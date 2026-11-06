"""Real SQLite contention and mocked GitHub restore, with no production data."""
import base64, gzip, importlib.util, json, os, sqlite3, tempfile, threading, time, unittest, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import collaboration as work
from git_backup import GitBackup

spec=importlib.util.spec_from_file_location('workspace_test_app',Path(__file__).with_name('app.py'))
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class DataCase(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();app.DATA=Path(self.temp.name)/'db';app.EXPORTS=Path(self.temp.name)/'out';app.init()
  with app.connect() as c:
   for i in range(5):c.execute('INSERT INTO samples(text,context,source,synthetic,fingerprint,created_at) VALUES(?,?,?,?,?,?)',('Câu '+str(i),'','test',True,str(i),app.now()))
 def tearDown(self):self.temp.cleanup()
 def test_parallel_claims_are_disjoint(self):
  barrier=threading.Barrier(5)
  def acquire(i):
   barrier.wait()
   with app.connect() as c:
    c.execute('BEGIN IMMEDIATE');return work.claim(c,{'client_id':str(i)*32,'reviewer':'user '+str(i)})['sample_id']
  with ThreadPoolExecutor(max_workers=5) as pool:ids=list(pool.map(acquire,range(5)))
  self.assertEqual(len(set(ids)),5)
 def test_foreign_and_expired_claims_cannot_write(self):
  a={'client_id':'a'*32,'reviewer':'A','sample_id':1};b=dict(a,client_id='b'*32)
  with app.connect() as c:
   work.claim(c,a)
   with self.assertRaises(work.Conflict):work.claim(c,b)
   with self.assertRaises(work.Conflict):work.save_draft(c,dict(b,draft={'reason':'bad'}),app.now())
   work.save_draft(c,dict(a,draft={'reason':'nháp đang gõ'}),app.now())
   c.execute('UPDATE work_claims SET expires_at=?',(time.time()-1,))
   with self.assertRaises(work.Conflict):work.check_claim(c,1,a)
   result=work.claim(c,b);self.assertIsNone(result['draft'])
   c.execute('UPDATE work_claims SET expires_at=?',(time.time()-1,))
   self.assertEqual(work.claim(c,a)['draft']['reason'],'nháp đang gõ')
 def test_private_snapshot_roundtrip_preserves_drafts_and_receipts(self):
  with app.connect() as c:
   work.claim(c,{'client_id':'a'*32,'reviewer':'A','sample_id':1})
   work.save_draft(c,{'client_id':'a'*32,'sample_id':1,'draft':{'reason':'đang viết'}},app.now())
   c.execute('INSERT INTO operations VALUES(?,?,?,?,?)',('d'*32,'/api/review','hash','{"saved":true}',app.now()))
   c.execute("UPDATE workspace_meta SET value='2' WHERE key='version'")
  with patch.dict(os.environ,{'GITHUB_BACKUP_REPO':'owner/private','GITHUB_BACKUP_TOKEN':'test-token'}):
   backup=GitBackup(app.DATA);remote={}
   def github(path,method='GET',body=None):
    if path=='/repos/owner/private':return {'private':True}
    if method=='PUT':remote.update(content=body['content'],sha='snapshot-sha');return {'content':{'sha':'snapshot-sha'}}
    return remote or None
   backup.request=github;backup.remote_file=lambda:remote or None
   result=backup.sync(app.connect);self.assertTrue(result['synced'])
   with tempfile.TemporaryDirectory() as restored:
    copy=GitBackup(Path(restored));copy.request=github;copy.remote_file=lambda:remote
    copy.restore_if_missing()
    with sqlite3.connect(Path(restored)/'studio.sqlite3') as c:
     self.assertEqual(c.execute('SELECT COUNT(*) FROM samples').fetchone()[0],5)
     self.assertEqual(c.execute('SELECT COUNT(*) FROM work_claims').fetchone()[0],0)
     self.assertEqual(c.execute('SELECT COUNT(*) FROM work_drafts').fetchone()[0],1)
     self.assertEqual(c.execute('SELECT COUNT(*) FROM operations').fetchone()[0],1)
 def test_public_or_unreachable_git_never_reports_synced(self):
  with patch.dict(os.environ,{'GITHUB_BACKUP_REPO':'owner/public','GITHUB_BACKUP_TOKEN':'test-token'}):
   b=GitBackup(app.DATA);b.request=lambda *a,**k:{'private':False}
   result=b.sync(app.connect);self.assertFalse(result['synced']);self.assertTrue(result['pending']);self.assertIn('public',result['error'])
   b.request=lambda *a,**k:(_ for _ in ()).throw(OSError('offline'))
   self.assertFalse(b.sync(app.connect)['synced'])
 def test_snapshot_refuses_remote_overwrite(self):
  with patch.dict(os.environ,{'GITHUB_BACKUP_REPO':'owner/private','GITHUB_BACKUP_TOKEN':'test-token'}):
   b=GitBackup(app.DATA);b.request=lambda *a,**k:{'private':True};b.remote_file=lambda:{'sha':'someone-else'};b.remote_sha='old'
   result=b.sync(app.connect);self.assertFalse(result['synced']);self.assertIn('instance',result['error'])

if __name__=='__main__':unittest.main(verbosity=2)
