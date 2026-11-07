"""Private GitHub snapshots; credentials stay in Render environment variables."""
import base64, gzip, io, json, os, re, sqlite3, tempfile, threading,shutil,time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

class GitBackup:
 def __init__(self,data):
  self.data=Path(data);self.repo=os.environ.get('GITHUB_BACKUP_REPO','').strip()
  self.token=os.environ.get('GITHUB_BACKUP_TOKEN','').strip();self.branch=os.environ.get('GITHUB_BACKUP_BRANCH','main')
  self.path='snapshots/latest.sqlite3.gz';self.last_success=None;self.last_version=-1;self.error=None
  self.remote_sha=None;self.lock=threading.Lock()
  self.wake=threading.Event();self.stopping=threading.Event();self.worker=None
 @property
 def configured(self):return bool(self.repo and self.token)
 def request_sync(self):
  # All writers share one worker. Never wait for GitHub on an annotation request.
  if self.configured:self.wake.set()
 def start_worker(self,connect,interval=20):
  if self.worker and self.worker.is_alive():return
  self.stopping.clear()
  def run():
   last_attempt=0
   while not self.stopping.is_set():
    self.wake.wait(interval);self.wake.clear()
    if self.stopping.is_set():break
    delay=max(0,last_attempt+interval-time.monotonic())
    if delay and self.stopping.wait(delay):break
    if self.configured:self.sync(connect)
    last_attempt=time.monotonic()
  self.worker=threading.Thread(target=run,daemon=True,name='studio-git-backup');self.worker.start()
 def stop_worker(self):
  self.stopping.set();self.wake.set()
  if self.worker:self.worker.join(timeout=5)
 def request(self,path,method='GET',body=None):
  req=Request('https://api.github.com'+path,data=json.dumps(body).encode() if body is not None else None,
   headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'Blacklist-Studio','X-GitHub-Api-Version':'2022-11-28'},method=method)
  with urlopen(req,timeout=15) as response:return json.load(response)
 def private_repo(self):
  if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',self.repo):raise ValueError('GITHUB_BACKUP_REPO cần dạng owner/repo.')
  meta=self.request('/repos/'+self.repo)
  if not meta.get('private'):raise ValueError('Repo backup đang public. Chuyển repo sang private trước khi sao lưu.')
 def remote_file(self):
  from urllib.parse import quote
  try:return self.request('/repos/'+self.repo+'/contents/'+self.path+'?ref='+quote(self.branch,safe=''))
  except HTTPError as e:
   if e.code==404:return None
   raise
 def restore_if_missing(self):
  if not self.configured:return
  self.private_repo();remote=self.remote_file()
  if not remote:return
  encoded=remote.get('content')
  if not encoded:encoded=self.request('/repos/'+self.repo+'/git/blobs/'+remote['sha'])['content']
  packed=base64.b64decode(encoded)
  self.data.mkdir(parents=True,exist_ok=True);temp=self.data/'restoring.sqlite3'
  try:
   with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream,temp.open('wb') as output:
    header=stream.read(16)
    if header!=b'SQLite format 3\x00':raise ValueError('Backup không phải SQLite hợp lệ.')
    output.write(header);size=len(header)
    while True:
     block=stream.read(1024*1024)
     if not block:break
     size+=len(block)
     if size>1024*1024*1024:raise ValueError('Backup vượt giới hạn phục hồi 1 GiB.')
     output.write(block)
   with sqlite3.connect(temp) as db:
    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup bị lỗi integrity.')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='samples'").fetchone():raise ValueError('Backup không phải dữ liệu Studio.')
   db.close()
   local=self.data/'studio.sqlite3'
   if local.exists():
    with sqlite3.connect(local) as current,sqlite3.connect(temp) as restored:
     a=dict(current.execute('SELECT key,value FROM workspace_meta'))
     b=dict(restored.execute('SELECT key,value FROM workspace_meta'))
     if a.get('database_id')!=b.get('database_id') or int(a['version'])<int(b['version']):
      raise ValueError('Database local không khớp backup mới nhất; cần phục hồi trước khi ghi.')
   else:temp.replace(local)
   self.remote_sha=remote['sha']
  finally:temp.unlink(missing_ok=True)
 def status(self,version):
  synced=self.configured and not self.error and self.last_version>=0 and version==self.last_version
  return {'version':version,'synced_version':self.last_version,'configured':self.configured,'repository':self.repo or None,'synced':bool(synced),
   'pending':self.configured and not synced,'last_success':self.last_success,'error':self.error,
   'message':self.error or ('Chưa nhập token backup trên Render.' if not self.configured else None)}
 def sync(self,connect,force=False):
  if not self.configured:return self.status(-1)
  with self.lock:
   try:
    if not force and self.last_version>=0 and not self.error:
     with connect() as current:
      version=int(current.execute("SELECT value FROM workspace_meta WHERE key='version'").fetchone()[0])
     if version==self.last_version:return self.status(version)
    self.private_repo()
    with tempfile.TemporaryDirectory() as temp:
     dest=Path(temp)/'snapshot.sqlite3'
     with connect() as source,sqlite3.connect(dest) as copy:
      source.backup(copy);version=int(copy.execute("SELECT value FROM workspace_meta WHERE key='version'").fetchone()[0])
      # Do not persist access leases. Drafts and operation receipts are retained.
      copy.execute('DELETE FROM work_claims')
      for table in ['auth_sessions','login_limits']:
       if copy.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():copy.execute('DELETE FROM '+table)
      copy.commit()
     copy.close();source.close()
     if version==self.last_version and not force:
      self.error=None;return self.status(version)
     archive=Path(temp)/'snapshot.sqlite3.gz'
     with dest.open('rb') as raw,gzip.open(archive,'wb',compresslevel=6) as compressed:shutil.copyfileobj(raw,compressed,length=1024*1024)
     if archive.stat().st_size>20_000_000:raise ValueError('Backup vượt 20 MB nén. Tải backup.sql và chuyển sang database lưu bền.')
     packed=archive.read_bytes()
    remote=self.remote_file();sha=remote['sha'] if remote else None
    if self.remote_sha is not None and sha!=self.remote_sha:raise ValueError('Backup đã thay đổi từ instance khác. Dừng ghi để tránh ghi đè; chỉ chạy một instance.')
    body={'message':'Studio snapshot '+datetime.now(timezone.utc).isoformat(),'branch':self.branch,'content':base64.b64encode(packed).decode()}
    if sha:body['sha']=sha
    result=self.request('/repos/'+self.repo+'/contents/'+self.path,'PUT',body)
    self.remote_sha=result['content']['sha'];self.last_version=version;self.last_success=datetime.now(timezone.utc).isoformat();self.error=None
    return self.status(version)
   except Exception as exc:
    # Never return URLs with credentials or request headers to clients/logs.
    self.error=('GitHub HTTP '+str(exc.code)+': kiểm tra token, quyền Contents và repo.' if isinstance(exc,HTTPError)
      else str(exc) if isinstance(exc,ValueError) else 'Chưa kết nối được GitHub. Dữ liệu đang chờ sao lưu; hệ thống sẽ thử lại.')
    return self.status(-1)
