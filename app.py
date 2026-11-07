"""Annotation workspace with SQLite, account permissions and PyArrow Parquet import."""
import base64, hmac
import csv, hashlib, io, json, os, re, sqlite3, unicodedata, uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import threading, time, shutil
import collaboration as work
import accounts as auth
import administration as adminwork
from git_backup import GitBackup
import parquet_import
import import_history
import blacklist_workflow
from native_parquet import NativeParquetImports,SCHEMA as NATIVE_IMPORT_SCHEMA

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('STUDIO_DATA',str(ROOT/'data')))
EXPORTS=Path(os.environ.get('STUDIO_EXPORTS',str(ROOT/'exports')))
CATEGORIES=dict(zip(['co_bac','lua_dao','spam','thu_ghet_xuc_pham','khieu_dam_bao_luc','hang_cam','tin_gia','an_ninh_chinh_tri','hai_tre_em'],['Cờ bạc','Lừa đảo','Spam','Thù ghét, xúc phạm','Khiêu dâm, bạo lực','Hàng cấm','Tin giả','An ninh, chính trị','Gây hại trẻ em']))
TOKEN=uuid.uuid4().hex
PASSWORD=os.environ.get('STUDIO_PASSWORD','')
USERNAME=os.environ.get('STUDIO_USERNAME','admin').strip().lower()
MUTATION_LOCK=threading.RLock()
EXPORT_LOCK=threading.Lock()
BACKUP=GitBackup(DATA)
PARQUET=parquet_import.ParquetUploads()

def now(): return datetime.now(timezone.utc).isoformat()
def dumps(v): return json.dumps(v,ensure_ascii=False,allow_nan=False)
def norm(s): return re.sub(r'\s+',' ',unicodedata.normalize('NFC',s)).strip().casefold()
def connect():
 c=sqlite3.connect(DATA/'studio.sqlite3',timeout=30);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.create_function('casefold',1,lambda value:(value or '').casefold(),deterministic=True);return c

def init():
 DATA.mkdir(parents=True,exist_ok=True);EXPORTS.mkdir(parents=True,exist_ok=True)
 with connect() as c:
  c.execute('PRAGMA journal_mode=WAL')
  c.executescript((ROOT/'sql/schema.sql').read_text(encoding='utf8'))
  c.executescript(work.SCHEMA)
  auth.migrate(c,USERNAME,PASSWORD,now())
  c.executescript(import_history.SCHEMA)
  c.executescript(NATIVE_IMPORT_SCHEMA)
  c.execute("UPDATE parquet_import_runs SET state='paused',error='Server đã khởi động lại. Chọn lại file để tiếp tục từ phần đã lưu.' WHERE state='running'")
  c.execute("INSERT OR IGNORE INTO workspace_meta VALUES('database_id',?)",(uuid.uuid4().hex,))
  c.executemany('INSERT OR IGNORE INTO categories VALUES(?,?)',CATEGORIES.items())

def require(ok,msg):
 if not ok: raise ValueError(msg)
def field(o,k,maximum=20000,required=False):
 s=o.get(k,'');require(isinstance(s,str),f'{k}: cần chuỗi văn bản');s=s.strip();require(len(s)<=maximum,f'{k}: quá dài');require(not required or bool(s),f'Thiếu {k}');return s

def contains(text,phrase):
 return bool(re.search(r'(?<!\w)'+re.escape(norm(phrase))+r'(?!\w)',norm(text)))

def evaluate(rule,text):
 cfg=rule['config'];kind=rule['kind'];matches=[]
 if kind=='exact':
  if norm(text)==norm(cfg['pattern']): matches=[text]
 elif kind in ('url','domain'):
  urls=re.findall(r'https?://[^\s<>"\']+',text,re.I)
  target=cfg['pattern'].casefold().rstrip('/')
  def url_key(value):
   part=urlsplit(value)
   return (part.scheme.casefold(),part.netloc.casefold(),part.path or '/',part.query)
  for u in urls:
   u=u.rstrip('.,;!?)')
   if kind=='url' and url_key(u)==url_key(cfg['pattern']):matches.append(u)
   if kind=='domain' and (urlsplit(u).hostname or '').casefold()==target:matches.append(u)
 else:
  for sentence in re.split(r'[.!?;\n]+',text):
   aa=[x for x in cfg['topic'] if contains(sentence,x)]
   bb=[x for x in cfg['behavior'] if contains(sentence,x)]
   if aa and bb:
    context=[x for x in cfg['context'] if contains(sentence,x)]
    matches.append({'topic':aa,'behavior':bb,'context':context})
 if not matches:return {'result':'NO_MATCH','evidence':[]}
 contextual=kind=='combined' and any(x['context'] for x in matches)
 return {'result':'CONTEXT_REVIEW' if contextual else 'MATCH','evidence':matches,
         'action':'REVIEW','note':'Chỉ là tín hiệu, không kết luận ý định hoặc tự động chặn.'}

def validate_rule(o):
 name=field(o,'name',200,True);category=field(o,'category',100,True);kind=field(o,'kind',30,True)
 require(category in CATEGORIES,'Nhãn không tồn tại');require(kind in ['exact','combined','url','domain'],'Kiểu luật không hợp lệ')
 cfg=o.get('config',{});require(isinstance(cfg,dict),'Điều kiện không hợp lệ')
 if kind=='combined':
  cfg={k:cfg.get(k,[]) for k in ['topic','behavior','context']}
  for k,v in cfg.items(): require(isinstance(v,list) and len(v)<=100 and all(isinstance(x,str) and 0<len(x.strip())<=200 for x in v),'Danh sách dấu hiệu không hợp lệ')
  require(cfg['topic'] and cfg['behavior'],'Cần dấu hiệu chủ đề và hành vi')
 else:
  cfg={'pattern':field(cfg,'pattern',20000,True)}
  if kind=='url':require(urlsplit(cfg['pattern']).scheme in ('http','https') and bool(urlsplit(cfg['pattern']).hostname),'URL cần có http:// hoặc https://')
  if kind=='domain':require(bool(re.fullmatch(r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',cfg['pattern'])),'Chỉ nhập tên miền, không có https:// hoặc đường dẫn')
 tests=o.get('tests',[]);require(isinstance(tests,list) and len(tests)<=100,'Danh sách kiểm tra không hợp lệ')
 clean=[]
 for t in tests:
  text=field(t,'text',20000,True);expected=field(t,'expected',30,True)
  require(expected in ['MATCH','NO_MATCH','CONTEXT_REVIEW'],'Kết quả mong muốn không hợp lệ');clean.append({'text':text,'expected':expected})
 rule={'name':name,'category':category,'kind':kind,'config':cfg,'tests':clean,
       'status':field(o,'status',30,True),'reviewer':field(o,'reviewer',100,True),'reason':field(o,'reason',2000,True),'source_sample_id':o.get('source_sample_id') or None,'intent':field(o,'intent',100),'evidence':field(o,'evidence',20000)}
 require(rule['status'] in ['draft','active','disabled'],'Trạng thái không hợp lệ')
 results=[dict(t,actual=evaluate(rule,t['text'])['result']) for t in clean]
 if rule['status']=='active':
  require(any(t['expected']=='MATCH' for t in clean) and any(t['expected'] in ['NO_MATCH','CONTEXT_REVIEW'] for t in clean),'Để bật: cần ít nhất mẫu bắt được và mẫu đối chiếu')
  require(all(t['actual']==t['expected'] for t in results),'Có câu kiểm tra chưa đạt')
 return rule,results

def sample_state(c,row):
 sample=dict(row);sid=sample['id'];review=c.execute('SELECT * FROM reviews WHERE sample_id=? ORDER BY revision DESC LIMIT 1',(sid,)).fetchone()
 sample['review']=dict(review) if review else None
 if review:sample['review']['labels']=json.loads(review['labels_json'])
 assignment=c.execute('SELECT * FROM task_assignments WHERE sample_id=?',(sid,)).fetchone()
 sample['assignment']=dict(assignment) if assignment else None
 sample['work_pending']=assignment['state']=='pending' if assignment else bool(sample['needs_review']) or not bool(review)
 audit=c.execute('SELECT a.* FROM review_audits a JOIN reviews r ON r.id=a.review_id WHERE r.sample_id=? ORDER BY r.revision DESC LIMIT 1',(sid,)).fetchone()
 sample['audit_note']=dict(audit) if audit else None
 return sample

def state(c,user=None,query=None):
 if not c.in_transaction:c.execute('BEGIN')
 query=query or {};page=max(0,int(query.get('page',['0'])[0]));size=100
 scope='s.archived_at IS NULL';args=[]
 if user and user['role']=='member':scope+=' AND a.user_id=?';args=[user['id']]
 joins=' FROM samples s LEFT JOIN task_assignments a ON a.sample_id=s.id LEFT JOIN reviews r ON r.id=(SELECT r2.id FROM reviews r2 WHERE r2.sample_id=s.id ORDER BY r2.revision DESC LIMIT 1)'
 pending="CASE WHEN a.sample_id IS NOT NULL THEN a.state='pending' ELSE s.needs_review=1 OR r.id IS NULL END"
 count=c.execute('SELECT COUNT(*),SUM('+pending+')'+joins+' WHERE '+scope,args).fetchone();total=count[0];waiting=count[1] or 0
 filtered=scope;params=list(args);q=query.get('q',[''])[0][:200];choice=query.get('filter',['all'])[0]
 if q:filtered+=' AND (instr(casefold(s.text),?)>0 OR CAST(s.id AS TEXT) LIKE ?)';params+=[q.casefold(),'%'+q+'%']
 if choice=='pending':filtered+=' AND ('+pending+')'
 elif choice in ['ALLOW','VIOLATION','UNSURE']:filtered+=' AND r.decision=?';params.append(choice)
 matched=c.execute('SELECT COUNT(*)'+joins+' WHERE '+filtered,params).fetchone()[0]
 samples=[sample_state(c,row) for row in c.execute('SELECT s.*'+joins+' WHERE '+filtered+' ORDER BY s.id DESC LIMIT ? OFFSET ?',params+[size,page*size])]
 rulequery='SELECT * FROM rules';ruleargs=[]
 if user and user['role']=='member':rulequery+=' WHERE created_by_user_id=?';ruleargs=[user['id']]
 rules=[]
 for row in c.execute(rulequery+' ORDER BY id DESC',ruleargs):
  rule=dict(row);rule['config']=json.loads(rule.pop('config_json'));rule['tests']=json.loads(rule.pop('tests_json'));rules.append(blacklist_workflow.details(c,rule))
 claims=[dict(r) for r in c.execute('SELECT sample_id,reviewer,expires_at FROM work_claims WHERE expires_at>?',(time.time(),))]
 allowed={sample['id'] for sample in samples};claims=[r for r in claims if r['sample_id'] in allowed]
 meta=dict(c.execute('SELECT key,value FROM workspace_meta'));backup=BACKUP.status(int(meta['version']))
 if user and user['role']=='member':backup={k:backup[k] for k in ['version','synced_version','configured','synced']}
 return {'categories':CATEGORIES,'samples':samples,'rules':rules,'claims':claims,'database_id':meta['database_id'],'backup':backup,
  'stats':{'total':total,'pending':waiting,'done':total-waiting,'active_rules':sum(r['status']=='active' for r in rules),'draft_rules':sum(r['status']=='draft' for r in rules)},
  'queue':{'page':page,'page_size':size,'total':matched}}

def atomic(path,text):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text,encoding='utf8');tmp.replace(path)
def export_all(c,only=None):
 # Build only the requested download, with one consistent read snapshot.
 # Annotation writes do not regenerate exports or hold this separate export lock.
 if not c.in_transaction:c.execute('BEGIN')
 if only is None or only in ['blacklist.json','blacklist_drafts.json']:
  stamp=now();rules=[]
  for row in c.execute('SELECT * FROM rules ORDER BY id DESC'):
   rule=dict(row);rule['config']=json.loads(rule.pop('config_json'));rule['tests']=json.loads(rule.pop('tests_json'));rules.append(blacklist_workflow.details(c,rule))
  if only is None or only=='blacklist.json':atomic(EXPORTS/'blacklist.json',dumps({'schema_version':1,'exported_at':stamp,'normalization':'NFC, whitespace, casefold; preserve accents','action':'REVIEW','rules':[r for r in rules if r['status']=='active']}))
  if only is None or only=='blacklist_drafts.json':atomic(EXPORTS/'blacklist_drafts.json',dumps({'exported_at':stamp,'rules':rules}))
 if only is None or only=='training_data.jsonl':
  target=EXPORTS/'training_data.jsonl';temp=target.with_suffix('.jsonl.tmp')
  with temp.open('w',encoding='utf8') as output:
   for row in c.execute("SELECT s.* FROM samples s WHERE s.archived_at IS NULL AND s.needs_review=0 AND EXISTS(SELECT 1 FROM reviews r WHERE r.sample_id=s.id)"):
    sample=dict(row);r=c.execute('SELECT * FROM reviews WHERE sample_id=? ORDER BY revision DESC LIMIT 1',(sample['id'],)).fetchone()
    if r['decision']=='UNSURE':continue
    labels=json.loads(r['labels_json'])
    data={'id':sample['id'],'text':sample['text'],'context':sample['context'],'source':sample['source'],'synthetic':bool(sample['synthetic']),'text_hash':sample['fingerprint'],'review_id':r['id'],'review_revision':r['revision'],'policy_version':r['policy_version'],'labels':labels,'label_mask':{k:int(v is not None) for k,v in labels.items()},'intent':r['intent'],'evidence':r['evidence'],'reason':r['reason']}
    output.write(dumps(data)+'\n')
  temp.replace(target)
 if only is None or only=='backup.sql':
  target=EXPORTS/'backup.sql';temp=target.with_suffix('.sql.tmp')
  with temp.open('w',encoding='utf8') as output:
   for line in c.iterdump():output.write(line+'\n')
  temp.replace(target)


def import_blacklist(c,o):
 rows=o.get('rules');require(isinstance(rows,list) and 0<len(rows)<=1000,'Cần 1–1000 mục blacklist')
 reviewer=field(o,'reviewer',100,True)
 known={(r['category'],r['kind'],dumps(json.loads(r['config_json']))) for r in c.execute('SELECT * FROM rules')}
 prepared=[];duplicates=0
 for i,row in enumerate(rows):
  require(isinstance(row,dict),f'Mục {i+1}: cần object')
  try:
   r,_=validate_rule(dict(row,status='draft',reviewer=reviewer,source_sample_id=None,reason=row.get('reason') or 'Nhập từ file blacklist'))
  except (ValueError,TypeError,KeyError) as e:raise ValueError(f'Mục {i+1}: {e}')
  key=(r['category'],r['kind'],dumps(r['config']))
  if key in known:duplicates+=1;continue
  known.add(key);prepared.append(r)
 if not o.get('preview',True):
  for r in prepared:
   args=(r['name'],r['category'],r['kind'],dumps(r['config']),dumps(r['tests']),'draft',1,None,reviewer,r['reason'],now())
   rid=c.execute('INSERT INTO rules(name,category,kind,config_json,tests_json,status,version,source_sample_id,reviewer,reason,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',args).lastrowid
   source_text=field(row,'source_text',20000);source_context=field(row,'source_context',20000)
   source_labels=row.get('source_labels',{});require(isinstance(source_labels,dict) and set(source_labels)<=set(CATEGORIES) and all(v is None or type(v) is int and v in [0,1] for v in source_labels.values()),'Nhãn nguồn tham khảo không hợp lệ')
   c.execute('UPDATE rules SET intent=?,evidence=?,source_text=?,source_context=?,source_labels_json=? WHERE id=?',(r['intent'],r['evidence'],source_text,source_context,dumps(source_labels),rid))
   c.execute('INSERT INTO rule_history(rule_id,version,snapshot_json,created_at) VALUES(?,?,?,?)',(rid,1,dumps(dict(r,id=rid,version=1,action='REVIEW')),now()))
 return {'preview':o.get('preview',True),'added':len(prepared),'duplicates':duplicates,'items':[{'name':r['name'],'kind':r['kind'],'category':r['category']} for r in prepared]}

NATIVE_IMPORTS=NativeParquetImports(PARQUET,connect,MUTATION_LOCK,BACKUP)

class Handler(BaseHTTPRequestHandler):
 def setup(self):
  super().setup();self.connection.settimeout(20);self.response_cookie=None;self.user=None
 def authorized(self):
  with connect() as c:self.user=auth.session(c,self.headers.get('Cookie'))
  if not self.user:self.reply({'error':'Hãy đăng nhập để vào không gian làm việc.'},401);return False
  return True
 def cookie(self,value,expire=False):
  secure='; Secure' if os.environ.get('RENDER') or self.headers.get('X-Forwarded-Proto')=='https' else ''
  self.response_cookie='studio_session='+value+'; Path=/; HttpOnly; SameSite=Lax; Max-Age='+('0' if expire else str(auth.SESSION_SECONDS))+secure
 def reply(self,obj,status=200,ctype='application/json; charset=utf-8',filename=None):
  data=(dumps(obj) if ctype.startswith('application/json') else obj).encode('utf8')
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
  if self.response_cookie:self.send_header('Set-Cookie',self.response_cookie)
  if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
  self.end_headers();self.wfile.write(data)
 def do_GET(self):
  parsed=urlsplit(self.path);path=parsed.path;query=parse_qs(parsed.query)
  if path=='/health':return self.reply({'status':'ok'})
  public_files={'/':'index.html','/app.js':'app.js','/admin.js':'admin.js','/parquet.js':'parquet.js','/style.css':'style.css'}
  if path in public_files:
   filename=public_files[path];ct='text/html' if path=='/' else 'text/css' if path.endswith('.css') else 'text/javascript'
   return self.reply((ROOT/'static'/filename).read_text(encoding='utf8'),ctype=ct+'; charset=utf-8')
  if not self.authorized():return
  try:
   if path.startswith('/api/admin/') or path in ['/api/history','/api/backup/status'] or path.startswith('/export/'):auth.admin(self.user)
   if path=='/api/state':
    with connect() as c:self.reply(state(c,self.user,query))
   elif path=='/api/sample':
    with connect() as c:
     sid=int(query.get('id',['0'])[0]);auth.sample_access(c,self.user,sid)
     self.reply(sample_state(c,c.execute('SELECT * FROM samples WHERE id=?',(sid,)).fetchone()))
   elif path=='/api/session':self.reply({'token':self.user['csrf'],'user':auth.public(self.user)})
   elif path=='/api/admin/overview':
    with connect() as c:self.reply(adminwork.overview(c))
   elif path=='/api/parquet/import/status':
    auth.admin(self.user);self.reply(NATIVE_IMPORTS.status(self.user['id'],query.get('batch_id',[None])[0]))
   elif path=='/api/admin/imports':
    with connect() as c:self.reply(import_history.list_batches(c,query.get('page',['0'])[0]))
   elif path=='/api/admin/samples':
    with connect() as c:self.reply(adminwork.sample_list(c,query))
   elif path=='/api/admin/reviews':
    with connect() as c:self.reply(adminwork.review_list(c,query))
   elif path=='/api/admin/review':
    with connect() as c:self.reply(adminwork.review_detail(c,int(query.get('id',['0'])[0])))
   elif path=='/api/backup/status':
    with connect() as c:self.reply(BACKUP.status(int(c.execute("SELECT value FROM workspace_meta WHERE key='version'").fetchone()[0])))
   elif path=='/api/history':
    with connect() as c:self.reply({'reviews':[dict(r) for r in c.execute('SELECT * FROM reviews ORDER BY id DESC LIMIT 500')],'rules':[dict(r) for r in c.execute('SELECT * FROM rule_history ORDER BY id DESC LIMIT 500')]})
   elif path.startswith('/export/'):
    filename=path.rsplit('/',1)[-1];require(filename in ['blacklist.json','blacklist_drafts.json','training_data.jsonl','backup.sql'],'File không hợp lệ')
    with EXPORT_LOCK:
     with connect() as c:export_all(c,filename)
     stream=(EXPORTS/filename).open('rb')
    with stream:
     self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.send_header('Content-Length',str(os.fstat(stream.fileno()).st_size));self.send_header('Content-Disposition','attachment; filename="'+filename+'"');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
     shutil.copyfileobj(stream,self.wfile,length=1024*1024)
   else:self.reply({'error':'Không tìm thấy'},404)
  except auth.Forbidden as e:self.reply({'error':str(e)},403)
  except ValueError as e:self.reply({'error':str(e)},400)
 def do_POST(self):
  self.received_at=time.time()
  self.handle_post()
 def handle_post(self):
  try:
   path=urlsplit(self.path).path
   if path=='/api/parquet/chunk':
    if not self.authorized():return
    auth.admin(self.user)
    require(hmac.compare_digest(self.headers.get('X-Studio-Token',''),self.user['csrf']),'Phiên hết hạn. Tải lại trang.')
    origin=self.headers.get('Origin');require(not origin or urlsplit(origin).netloc==self.headers.get('Host'),'Nguồn yêu cầu không hợp lệ.')
    require(self.headers.get('Content-Type','').split(';')[0]=='application/octet-stream','Khối Parquet cần application/octet-stream.')
    n=int(self.headers.get('Content-Length','0'));require(0<n<=parquet_import.CHUNK_BYTES,'Khối tải lên tối đa 1 MiB.')
    query=parse_qs(urlsplit(self.path).query);key=query.get('upload_id',[''])[0];offset=int(query.get('offset',['-1'])[0])
    PARQUET.get(key,self.user['id']);data=self.rfile.read(n);require(len(data)==n,'Khối tải lên chưa hoàn tất.')
    with MUTATION_LOCK:result=PARQUET.append(key,self.user['id'],offset,data)
    return self.reply(result)
   require(self.headers.get('Content-Type','').split(';')[0]=='application/json','Yêu cầu cần Content-Type application/json.')
   origin=self.headers.get('Origin')
   require(not origin or urlsplit(origin).netloc==self.headers.get('Host'),'Nguồn yêu cầu không hợp lệ.')
   n=int(self.headers.get('Content-Length','0'));require(0<n<=2_000_000,'Yêu cầu quá lớn hoặc rỗng')
   o=json.loads(self.rfile.read(n));require(isinstance(o,dict),'Cần JSON object')
   if path=='/api/auth/login':
    with connect() as c:logged=auth.login(c,o,self.client_address[0])
    if not logged:return self.reply({'error':'Tài khoản hoặc mã đăng nhập không đúng.'},401)
    self.cookie(logged.pop('cookie'));return self.reply(logged)
   if not self.authorized():return
   require(hmac.compare_digest(self.headers.get('X-Studio-Token',''),self.user['csrf']),'Phiên hết hạn. Tải lại trang.')
   if path.startswith(('/api/admin/','/api/parquet/')) or path in ['/api/import','/api/blacklist/import','/api/backup/sync']:auth.admin(self.user)
   if path=='/api/parquet/import/start':
    with MUTATION_LOCK:result=NATIVE_IMPORTS.start(auth.public(self.user),o)
    return self.reply(result)
   if path=='/api/parquet/import/pause':return self.reply(NATIVE_IMPORTS.pause(self.user['id'],o.get('batch_id')))
   if path.startswith('/api/parquet/'):
    with MUTATION_LOCK:result=PARQUET.action(path,self.user['id'],o)
    return self.reply(result)
   raw_client=o.get('client_id','')
   require(isinstance(raw_client,str) and bool(re.fullmatch(r'[a-f0-9]{32,64}',raw_client)),'Thiếu mã phiên làm việc.')
   o['client_id']=hashlib.sha256((str(self.user['id'])+':'+raw_client).encode()).hexdigest()
   o['reviewer']=self.user['display_name'];o['_user']=auth.public(self.user);o['_received_at']=self.received_at
   result={};changed=False
   opid=o.get('operation_id');cached=None
   if opid is not None:require(isinstance(opid,str) and bool(re.fullmatch(r'[a-f0-9]{32,64}',opid)),'Mã thao tác không hợp lệ.')
   signature={k:v for k,v in o.items() if k not in ['_user','reviewer','_received_at']}
   signature['_actor_id']=self.user['id']
   request_hash=hashlib.sha256(dumps(signature).encode()).hexdigest()
   with MUTATION_LOCK,connect() as c:
    c.execute('BEGIN IMMEDIATE')
    if opid:cached=c.execute('SELECT * FROM operations WHERE id=?',(opid,)).fetchone()
    if cached:
     require(cached['kind']==path and cached['request_hash']==request_hash,'Mã thao tác đã dùng cho nội dung hoặc tài khoản khác.')
     result=json.loads(cached['result_json'])
     if path=='/api/review':
      c.execute('DELETE FROM work_claims WHERE sample_id=? AND owner=?',(o.get('sample_id'),work.owner(o)))
      c.execute('UPDATE annotation_attempts SET closed_at=? WHERE owner=? AND sample_id=? AND closed_at IS NULL',(time.time(),work.owner(o),o.get('sample_id')))
    elif path=='/api/auth/logout':
     c.execute('DELETE FROM auth_sessions WHERE token_hash=?',(self.user['token_hash'],))
     c.execute('DELETE FROM work_claims WHERE owner=?',(work.owner(o),));self.cookie('',expire=True);result={'logged_out':True}
    elif path=='/api/admin/users':result=auth.create_member(c,o,now());changed=True
    elif path in ['/api/admin/users/rotate','/api/admin/users/toggle','/api/admin/users/reclaim','/api/admin/users/edit','/api/admin/users/delete','/api/admin/users/restore']:result=adminwork.manage_user(c,path,o,self.user,now());changed=True
    elif path in ['/api/admin/samples/edit','/api/admin/samples/delete','/api/admin/samples/restore']:result=adminwork.edit_sample(c,path,o,self.user,now());changed=True
    elif path in ['/api/admin/imports/undo','/api/admin/imports/restore']:result=import_history.change(c,path.rsplit('/',1)[-1],o,now());changed=True
    elif path=='/api/admin/assign/preview':result=adminwork.assignment_plan(c,o)
    elif path=='/api/admin/assign':result=adminwork.apply_plan(c,o,self.user,now());changed=True
    elif path=='/api/admin/settings':
     seconds=o.get('fast_seconds');require(type(seconds) in [int,float] and 1<=seconds<=120,'Ngưỡng cần từ 1 đến 120 giây.')
     c.execute("UPDATE workspace_meta SET value=? WHERE key='fast_seconds'",(str(seconds),));result={'updated':True};changed=True
    elif path=='/api/admin/audit':result=adminwork.audit_review(c,o,self.user,now());changed=True
    elif path=='/api/work/claim':
     result=work.claim(c,o)
     if result.get('sample_id'):result['sample']=sample_state(c,c.execute('SELECT * FROM samples WHERE id=?',(result['sample_id'],)).fetchone())
    elif path=='/api/work/heartbeat':work.heartbeat(c,o);result={'held':True}
    elif path=='/api/draft':changed=work.save_draft(c,o,now());result={'draft_saved':True}
    elif path=='/api/backup/sync':result={'requested':True}
    elif path=='/api/blacklist/import':result=import_blacklist(c,o)
    elif path=='/api/import':
     rows=o.get('rows',[]);require(isinstance(rows,list) and 0<len(rows)<=1000,'Mỗi lần nhập 1–1000 mẫu')
     batch_id=import_history.begin(c,o,self.user,now())
     result=import_history.store_rows(c,rows,batch_id,now())
    elif path=='/api/review':
     sid=o.get('sample_id');sample=c.execute('SELECT * FROM samples WHERE id=?',(sid,)).fetchone();require(sample is not None,'Không có mẫu')
     work.check_claim(c,sid,o)
     auth.sample_access(c,self.user,sid,claim=True)
     timing=work.finish_timing(c,o)
     previous=c.execute('SELECT MAX(revision) FROM reviews WHERE sample_id=?',(sid,)).fetchone()[0] or 0
     require(o.get('base_revision',0)==previous,'Mẫu đã thay đổi ở cửa sổ khác. Tải lại trước khi lưu.')
     decision=field(o,'decision',30,True);require(decision in ['ALLOW','VIOLATION','UNSURE'],'Quyết định không hợp lệ')
     labels=o.get('labels',{});require(isinstance(labels,dict) and set(labels)==set(CATEGORIES),'Cần đủ 9 trường nhãn')
     require(all(v is None or type(v) is int and v in [0,1] for v in labels.values()),'Nhãn phải là 0, 1 hoặc null')
     if decision=='VIOLATION':require(1 in labels.values(),'Vi phạm cần ít nhất một nhãn Có')
     if decision=='ALLOW':require(1 not in labels.values() and 0 in labels.values(),'Hợp lệ cần ít nhất một nhóm đã kiểm tra Không')
     evidence=field(o,'evidence');require(not evidence or evidence in sample['text'],'Bằng chứng phải là đoạn có trong câu gốc')
     reviewer=field(o,'reviewer',100,True);reason=field(o,'reason',2000) or decision+' · '+', '.join(k for k,v in labels.items() if v==1);intent=field(o,'intent',100)
     cursor=c.execute('INSERT INTO reviews(sample_id,revision,decision,labels_json,intent,evidence,reason,reviewer,policy_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(sid,previous+1,decision,dumps(labels),intent,evidence,reason,reviewer,'demo-1',now()));result={'saved':True,'review_id':cursor.lastrowid}
     c.execute('UPDATE reviews SET user_id=?,attempt_id=?,elapsed_ms=?,active_ms=?,fast_flag=?,threshold_ms=? WHERE id=?',(self.user['id'],timing['attempt_id'],timing['elapsed_ms'],timing['active_ms'],timing['fast_flag'],timing['threshold_ms'],cursor.lastrowid))
     c.execute('UPDATE samples SET needs_review=0 WHERE id=?',(sid,))
     c.execute("UPDATE task_assignments SET state='done' WHERE sample_id=?",(sid,))
     if o.get('propose_rule') is True and decision=='VIOLATION':
      result.update(blacklist_workflow.propose(c,auth.public(self.user),{'sample_id':sid,'review_id':cursor.lastrowid,'candidate_evidence':o.get('candidate_evidence','')},now()))
     c.execute('DELETE FROM work_drafts WHERE owner=? AND sample_id=?',(work.owner(o),sid))
     c.execute('DELETE FROM work_claims WHERE sample_id=?',(sid,))
    elif path=='/api/blacklist/propose':
     result=blacklist_workflow.propose(c,auth.public(self.user),o,now());changed=any(p['created'] for p in result['proposals'])
    elif path=='/api/rule':
     if self.user['role']=='member':
      source=o.get('source_sample_id');auth.sample_access(c,self.user,source)
      if o.get('status')!='draft':raise auth.Forbidden('Thành viên chỉ được gửi blacklist ở trạng thái nháp để admin duyệt.')
      latest_review=c.execute('SELECT * FROM reviews WHERE sample_id=? ORDER BY revision DESC LIMIT 1',(source,)).fetchone()
      require(latest_review and latest_review['user_id']==self.user['id'] and latest_review['decision']=='VIOLATION','Cần nhãn Vi phạm mới nhất từ phần việc của bạn.')
      require(json.loads(latest_review['labels_json']).get(o.get('category'))==1,'Nhóm blacklist phải là nhóm vi phạm đã gán cho câu này.')
      if o.get('id'):
       previous_rule=c.execute('SELECT * FROM rules WHERE id=?',(o['id'],)).fetchone()
       if not previous_rule or previous_rule['created_by_user_id']!=self.user['id'] or previous_rule['status']!='draft':raise auth.Forbidden('Bạn chỉ sửa được blacklist nháp do mình tạo.')
     r,tests=validate_rule(o);rid=o.get('id');version=1
     if rid:
      old=c.execute('SELECT version FROM rules WHERE id=?',(rid,)).fetchone();require(old is not None,'Không có luật');require(o.get('version')==old[0],'Luật đã thay đổi. Tải lại.');version=old[0]+1
     existing_rule=c.execute('SELECT * FROM rules WHERE id=?',(rid,)).fetchone() if rid else None
     blacklist_workflow.validate_evidence(c,r,existing_rule)
     args=(r['name'],r['category'],r['kind'],dumps(r['config']),dumps(r['tests']),r['status'],version,r['source_sample_id'],r['reviewer'],r['reason'],now())
     if rid:c.execute('UPDATE rules SET name=?,category=?,kind=?,config_json=?,tests_json=?,status=?,version=?,source_sample_id=?,reviewer=?,reason=?,updated_at=? WHERE id=?',args+(rid,))
     else:rid=c.execute('INSERT INTO rules(name,category,kind,config_json,tests_json,status,version,source_sample_id,reviewer,reason,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',args).lastrowid
     if not o.get('id'):c.execute('UPDATE rules SET created_by_user_id=? WHERE id=?',(self.user['id'],rid))
     c.execute('UPDATE rules SET intent=?,evidence=? WHERE id=?',(r['intent'],r['evidence'],rid))
     snapshot=dict(r,id=rid,version=version,action='REVIEW');c.execute('INSERT INTO rule_history(rule_id,version,snapshot_json,created_at) VALUES(?,?,?,?)',(rid,version,dumps(snapshot),now()));result={'id':rid,'version':version,'tests':tests}
    elif path=='/api/test':
     r,tests=validate_rule(dict(o['rule'],status='draft'));result={'tests':tests,'probe':evaluate(r,field(o,'text',20000))}
    else:raise ValueError('API không tồn tại')
    if not cached:
     changed=changed or path in ['/api/import','/api/review','/api/rule'] or path=='/api/blacklist/import' and not o.get('preview',True)
     if opid and changed:
      receipt={k:v for k,v in result.items() if k!='login_code'}
      if 'login_code' in result:receipt['code_once']=True
      c.execute('INSERT INTO operations VALUES(?,?,?,?,?)',(opid,path,request_hash,dumps(receipt),now()))
     if changed:c.execute("UPDATE workspace_meta SET value=CAST(value AS INTEGER)+1 WHERE key='version'")
   if path=='/api/backup/sync':BACKUP.sync(connect,force=True)
   elif changed or cached:BACKUP.request_sync()
   if changed or cached or path=='/api/backup/sync':
    with connect() as c:result['backup']=BACKUP.status(int(c.execute("SELECT value FROM workspace_meta WHERE key='version'").fetchone()[0]))
   self.reply(result)
  except parquet_import.UploadExpired as e:self.reply({'error':str(e),'upload_expired':True},410)
  except parquet_import.UploadConflict as e:self.reply({'error':str(e)},409)
  except auth.Forbidden as e:self.reply({'error':str(e)},403)
  except auth.RateLimited as e:self.reply({'error':str(e)},429)
  except work.Conflict as e:self.reply({'error':str(e),'conflict':True},409)
  except (ValueError,TypeError,KeyError,sqlite3.IntegrityError) as e:self.reply({'error':str(e)},400)
  except Exception:
   import traceback;traceback.print_exc();self.reply({'error':'Lỗi máy chủ; nháp được giữ. Kiểm tra log trước khi thử lại.'},500)

if __name__=='__main__':
 if not PASSWORD:raise SystemExit('Set STUDIO_PASSWORD before deploying')
 try:BACKUP.restore_if_missing()
 except Exception:raise SystemExit('Không thể khôi phục Git backup. Kiểm tra repo private, token và kết nối; server dừng để tránh ghi đè dữ liệu cũ.')
 init()
 BACKUP.start_worker(connect)
 port=int(os.environ.get('PORT','8765'))
 print(f'Blacklist Studio: http://127.0.0.1:{port} — Ctrl+C để dừng',flush=True)
 ThreadingHTTPServer((os.environ.get('HOST','0.0.0.0'),port),Handler).serve_forever()
