"""Server-side full-file imports with committed checkpoints and resumable workers."""
import hashlib,itertools,json,threading,time,uuid
from datetime import datetime,timezone
from pathlib import Path
import import_history
from collaboration import Conflict
from parquet_import import UploadExpired

SCHEMA=(Path(__file__).parent/'sql/006_parquet_jobs.sql').read_text(encoding='utf8')
BATCH_ROWS=1000

def now():return datetime.now(timezone.utc).isoformat()

class NativeParquetImports:
 def __init__(self,uploads,connect,lock,backup):
  self.uploads=uploads;self.connect=connect;self.lock=lock;self.backup=backup;self.workers={}
 def status(self,user_id,batch_id=None):
  with self.connect() as c:
   if batch_id:row=c.execute('SELECT * FROM parquet_import_runs WHERE batch_id=? AND user_id=?',(batch_id,user_id)).fetchone()
   else:row=c.execute('SELECT * FROM parquet_import_runs WHERE user_id=? ORDER BY updated_at DESC LIMIT 1',(user_id,)).fetchone()
   if not row:return {'run':None}
   run=dict(row);run.pop('signature',None);run['options']=json.loads(run.pop('options_json'));run['percent']=round(run['processed']/run['total']*100,1) if run['total'] else 100
   version=int(c.execute("SELECT value FROM workspace_meta WHERE key='version'").fetchone()[0])
  worker=self.workers.get(run['batch_id']);run['worker_active']=bool(worker and worker['thread'].is_alive());run['pause_requested']=bool(worker and worker['stop'].is_set());run['file_available']=bool(worker and worker['upload_id'] in self.uploads.jobs);run['upload_id']=worker['upload_id'] if run['file_available'] else None
  return {'run':run,'backup':self.backup.status(version)}
 def start(self,user,o):
  job=self.uploads.get(o.get('upload_id'),user['id'])
  options=self.uploads.options(job,dict(o,all_rows=True));meta=self.uploads.metadata(job)
  requested=o.get('import_batch_id') or uuid.uuid4().hex
  digest=hashlib.sha256(json.dumps({'file':meta['sha256'],'name':job['name'],'options':options},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  # One active worker per service keeps the free instance's memory bounded.
  for bid,worker in self.workers.items():
   if worker['thread'].is_alive():
    if worker['user_id']==user['id'] and worker['signature']==digest:return self.status(user['id'],bid)
    raise Conflict('Đang nhập một file. Tạm dừng hoặc chờ file đó xong trước khi nhập file khác.')
  with self.connect() as c:
   c.execute('BEGIN IMMEDIATE')
   existing=c.execute('SELECT * FROM parquet_import_runs WHERE batch_id=?',(requested,)).fetchone()
   if existing and (existing['user_id']!=user['id'] or existing['signature']!=digest):raise Conflict('Mã đợt nhập đã dùng cho file hoặc cột khác.')
   if not existing:existing=c.execute("SELECT * FROM parquet_import_runs WHERE user_id=? AND signature=? AND state IN ('paused','error','running') ORDER BY updated_at DESC LIMIT 1",(user['id'],digest)).fetchone()
   if existing:
    bid=existing['batch_id']
    batch=c.execute('SELECT status FROM import_batches WHERE id=?',(bid,)).fetchone()
    if batch['status']!='active':raise Conflict('Đợt này đã hoàn tác. Khôi phục đợt trước khi tiếp tục.')
    if existing['state']=='done':return self.status(user['id'],bid)
    c.execute("UPDATE parquet_import_runs SET state='running',error=NULL,updated_at=? WHERE batch_id=?",(now(),bid))
   else:
    bid=import_history.begin(c,{'import_batch_id':requested,'import_name':job['name']+' · cột '+options['mapping']['text']},user,now())
    c.execute("INSERT INTO parquet_import_runs(batch_id,user_id,file_name,signature,options_json,total,state,created_at,updated_at) VALUES(?,?,?,?,?,?,'running',?,?)",(bid,user['id'],job['name'],digest,json.dumps(options,ensure_ascii=False),meta['rows'],now(),now()))
   c.execute("UPDATE workspace_meta SET value=CAST(value AS INTEGER)+1 WHERE key='version'")
  stop=threading.Event();thread=threading.Thread(target=self.run,args=(bid,o['upload_id'],user,stop),daemon=True)
  self.workers[bid]={'thread':thread,'stop':stop,'upload_id':o['upload_id'],'user_id':user['id'],'signature':digest}
  job['import_running']=True;thread.start()
  return self.status(user['id'],bid)
 def pause(self,user_id,batch_id):
  result=self.status(user_id,batch_id)
  if not result['run']:raise ValueError('Không có lần nhập này.')
  worker=self.workers.get(batch_id)
  if worker and worker['thread'].is_alive():worker['stop'].set()
  return result
 def run(self,bid,upload_id,user,stop):
  iterator=None;job=None;error=None;last_backup=time.monotonic();final_state='paused'
  try:
   job=self.uploads.get(upload_id,user['id'])
   with self.connect() as c:row=dict(c.execute('SELECT * FROM parquet_import_runs WHERE batch_id=?',(bid,)).fetchone())
   options=json.loads(row['options_json']);options['start']=row['processed']
   iterator=self.uploads.rows(job,options)
   while not stop.is_set():
    items=list(itertools.islice(iterator,BATCH_ROWS))
    if not items:final_state='done';break
    samples=[r['sample'] for r in items if 'sample' in r];stamp=now()
    with self.lock,self.connect() as c:
     c.execute('BEGIN IMMEDIATE')
     import_history.begin(c,{'import_batch_id':bid,'import_name':job['name']},user,stamp)
     result=import_history.store_rows(c,samples,bid,stamp)
     c.execute('''UPDATE parquet_import_runs SET processed=processed+?,added=added+?,duplicates=duplicates+?,
      skipped_empty=skipped_empty+?,skipped_too_long=skipped_too_long+?,updated_at=? WHERE batch_id=?''',
      (len(items),result['added'],result['duplicates'],sum(r.get('skip')=='empty' for r in items),sum(r.get('skip')=='too_long' for r in items),stamp,bid))
     c.execute("UPDATE workspace_meta SET value=CAST(value AS INTEGER)+1 WHERE key='version'")
    job['touched']=time.time()
    if self.backup.configured and time.monotonic()-last_backup>=20:
     with self.lock:self.backup.sync(self.connect)
     last_backup=time.monotonic()
    # Brief yield between commits keeps annotation/heartbeat requests responsive.
    stop.wait(.005)
   with self.connect() as c:
    row=c.execute('SELECT processed,total FROM parquet_import_runs WHERE batch_id=?',(bid,)).fetchone()
    if row['processed']>=row['total']:final_state='done'
  except Exception as exc:
   final_state='error';error=str(exc) if isinstance(exc,(ValueError,Conflict)) else 'Không thể nhập tiếp. Các lô đã lưu vẫn được giữ; chọn lại file để tiếp tục hoặc hoàn tác đợt.'
  finally:
   if iterator:iterator.close()
   with self.lock,self.connect() as c:
    c.execute('UPDATE parquet_import_runs SET state=?,error=?,updated_at=? WHERE batch_id=?',(final_state,error,now(),bid))
    c.execute("UPDATE workspace_meta SET value=CAST(value AS INTEGER)+1 WHERE key='version'")
   if job:job['import_running']=False;job['touched']=time.time()
   if self.backup.configured:
    with self.lock:self.backup.sync(self.connect)
