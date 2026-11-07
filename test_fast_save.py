"""A blocked backup/download must not block another user's annotation writes."""
import importlib.util,json,os,threading,time,unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from http_test_support import Client

class FastSave(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
  spec=importlib.util.spec_from_file_location('fast_test_app',Path(__file__).with_name('app.py'))
  self.app=importlib.util.module_from_spec(spec)
  with patch.dict(os.environ,{'STUDIO_PASSWORD':'test-only-password','STUDIO_USERNAME':'admin','STUDIO_DATA':str(self.root/'data'),'STUDIO_EXPORTS':str(self.root/'exports'),'GITHUB_BACKUP_TOKEN':'','RENDER':''}):spec.loader.exec_module(self.app)
  self.app.init()
  class Quiet(self.app.Handler):
   def log_message(self,*args):pass
  self.http=ThreadingHTTPServer(('127.0.0.1',0),Quiet);self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
  self.base='http://127.0.0.1:'+str(self.http.server_port);self.admin=Client(self.base)
  account=self.admin.call('/api/admin/users',{'username':'worker','display_name':'Người gán nhãn'})
  self.member=Client(self.base,'worker',account['login_code'])
  self.admin.call('/api/import',{'rows':[{'text':'Câu kiểm thử '+str(i),'source':'test','synthetic':True} for i in range(3)]})
  self.admin.call('/api/admin/assign',{'plan':[{'user_id':self.member.user['id'],'sample_ids':[1,2,3]}]})
  self.release=threading.Event();self.started=threading.Event();self.backup=self.app.BACKUP
  self.backup.repo='test/private';self.backup.token='test-placeholder'
  def slow_backup(connect,force=False):
   self.started.set();self.release.wait(8)
   with connect() as c:version=int(c.execute("SELECT value FROM workspace_meta WHERE key='version'").fetchone()[0])
   self.backup.last_version=version
   return self.backup.status(version)
  self.backup.sync=slow_backup
 def tearDown(self):
  self.release.set();self.backup.stop_worker();self.http.shutdown();self.http.server_close();self.thread.join(timeout=2);self.temp.cleanup()
 def save(self,sample_id=1,base=0,decision='VIOLATION'):
  claimed=self.member.call('/api/work/claim',{'sample_id':sample_id})
  self.assertEqual(claimed['sample']['id'],sample_id)
  labels={k:None for k in self.app.CATEGORIES};labels['spam']=1 if decision=='VIOLATION' else 0
  return self.member.call('/api/review',{'sample_id':sample_id,'base_revision':base,'decision':decision,'labels':labels,'propose_rule':decision=='VIOLATION'})
 def test_background_git_stall_does_not_block_save_or_next_claim(self):
  self.backup.start_worker(self.app.connect,interval=.05);self.backup.request_sync();self.assertTrue(self.started.wait(2))
  # Calling export_all on this path is a regression, even if a tiny fixture is fast.
  with patch.object(self.app,'export_all',side_effect=AssertionError('Must not export on save')):
   with ThreadPoolExecutor(max_workers=1) as pool:
    began=time.monotonic();result=pool.submit(self.save).result(timeout=2);elapsed=time.monotonic()-began
   self.assertFalse(self.release.is_set());self.assertTrue(result['saved']);self.assertFalse(result['backup']['synced']);self.assertTrue(result['proposals'])
   next_work=self.member.call('/api/work/claim',{});self.assertEqual(next_work['sample']['id'],2)
   self.assertEqual(list((self.root/'exports').iterdir()),[])
   print('\nBlocked-backup benchmark: save + explicit claim %.1f ms; Git still blocked.'%(elapsed*1000))
 def test_manual_git_sync_does_not_hold_global_write_lock(self):
  with ThreadPoolExecutor(max_workers=2) as pool:
   manual=pool.submit(self.admin.call,'/api/backup/sync',{})
   self.assertTrue(self.started.wait(2))
   result=pool.submit(self.save).result(timeout=2);self.assertTrue(result['saved']);self.assertFalse(manual.done())
   self.release.set();self.assertTrue(manual.result(timeout=2)['backup']['synced'])
 def test_downloads_are_current_and_generate_only_requested_file(self):
  self.save();self.assertEqual(list((self.root/'exports').iterdir()),[])
  def download(name):
   with self.admin.opener.open(self.base+'/export/'+name,timeout=5) as response:return response.read().decode()
  first=[json.loads(line) for line in download('training_data.jsonl').splitlines()];self.assertEqual(first[0]['review_revision'],1)
  self.assertEqual([p.name for p in (self.root/'exports').iterdir()],['training_data.jsonl'])
  self.save(base=1,decision='ALLOW')
  second=[json.loads(line) for line in download('training_data.jsonl').splitlines()];self.assertEqual(second[0]['review_revision'],2);self.assertEqual(second[0]['labels']['spam'],0)
  self.assertIn('CREATE TABLE',download('backup.sql'))

if __name__=='__main__':unittest.main(verbosity=2)
