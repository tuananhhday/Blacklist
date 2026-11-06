import json,os,sqlite3,subprocess,sys,tempfile,time,unittest,uuid
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import pyarrow as pa
import pyarrow.parquet as pq
from http_test_support import Server,Client

class NativeFullFile(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.server=Server(18773)
 @classmethod
 def tearDownClass(cls):cls.server.close()
 def setUp(self):self.admin=Client(self.server.base)
 def upload(self,data,name='train.parquet'):
  started=self.admin.call('/api/parquet/start',{'name':name,'size':len(data)});key=started['upload_id']
  for offset in range(0,len(data),started['chunk_bytes']):
   block=data[offset:offset+started['chunk_bytes']]
   req=Request(self.server.base+'/api/parquet/chunk?upload_id='+key+'&offset='+str(offset),data=block,headers={'Content-Type':'application/octet-stream','X-Studio-Token':self.admin.token})
   with self.admin.opener.open(req) as response:json.load(response)
  return key
 def file(self,values,extra=None):
  sink=pa.BufferOutputStream();data={'Comment':values,'label':[0]*len(values)}
  if extra:data.update(extra)
  pq.write_table(pa.table(data),sink,compression='zstd',row_group_size=1024);return sink.getvalue().to_pybytes()
 def wait(self,bid,states):
  deadline=time.monotonic()+20
  while time.monotonic()<deadline:
   status=self.admin.call('/api/parquet/import/status?batch_id='+bid)
   if status['run']['state'] in states and not status['run']['worker_active']:return status['run']
   time.sleep(.02)
  self.fail('Import did not reach '+str(states))
 def test_full_file_over_5000_rows_click_columns_and_one_undo(self):
  prefix=uuid.uuid4().hex;values=[prefix+' câu '+str(i) for i in range(6201)];values[1]=None;values[2]='';values[3]='x'*20001
  self.admin.call('/api/import',{'rows':[{'text':values[0],'source':'preexisting','synthetic':False}]})
  before=self.admin.call('/api/state')['stats']['total'];key=self.upload(self.file(values,{'Other':['khác '+str(i) for i in range(len(values))]}))
  table=self.admin.call('/api/parquet/table',{'upload_id':key});self.assertEqual(len(table['rows']),8);self.assertTrue(next(c for c in table['columns'] if c['name']=='Comment')['text_compatible']);self.assertFalse(next(c for c in table['columns'] if c['name']=='label')['text_compatible'])
  bid=uuid.uuid4().hex;body={'upload_id':key,'text_column':'Comment','all_rows':True,'import_batch_id':bid}
  first=self.admin.call('/api/parquet/import/start',body);self.assertEqual(first['run']['total'],6201)
  self.admin.call('/api/parquet/import/start',body)
  done=self.wait(bid,{'done'});self.assertEqual(done['processed'],6201);self.assertEqual(done['added'],6197);self.assertEqual(done['duplicates'],1);self.assertEqual(done['skipped_empty'],2);self.assertEqual(done['skipped_too_long'],1)
  state=self.admin.call('/api/state');self.assertEqual(state['stats']['total'],before+6197);self.assertLessEqual(len(state['samples']),100);self.assertGreater(state['queue']['total'],5000)
  with sqlite3.connect(self.server.root/'data/studio.sqlite3') as c:sid=c.execute('SELECT id FROM samples WHERE text=?',(prefix+' câu 4',)).fetchone()[0]
  self.assertNotIn(sid,{s['id'] for s in state['samples']});single=self.admin.call('/api/sample?id='+str(sid));self.assertEqual(single['text'],prefix+' câu 4')
  self.assertEqual(self.admin.call('/api/parquet/import/start',body)['run']['added'],6197)
  self.assertEqual(self.admin.call('/api/admin/imports/undo',{'batch_id':bid})['changed'],6197)
  self.assertEqual(self.admin.call('/api/state')['stats']['total'],before)
  self.assertEqual(self.admin.call('/api/admin/imports/restore',{'batch_id':bid})['changed'],6197)
 def test_pause_restart_reupload_and_resume_checkpoint(self):
  prefix=uuid.uuid4().hex;data=self.file([prefix+' item '+str(i) for i in range(30001)]);key=self.upload(data,'resume.parquet');bid=uuid.uuid4().hex
  self.admin.call('/api/parquet/import/start',{'upload_id':key,'text_column':'Comment','import_batch_id':bid})
  for _ in range(200):
   status=self.admin.call('/api/parquet/import/status?batch_id='+bid)['run']
   if status['processed']>=1000:break
   time.sleep(.005)
  self.admin.call('/api/parquet/import/pause',{'batch_id':bid});paused=self.wait(bid,{'paused'});self.assertGreaterEqual(paused['processed'],1000);self.assertLess(paused['processed'],30001)
  with sqlite3.connect(self.server.root/'data/studio.sqlite3') as c:c.execute("UPDATE parquet_import_runs SET state='running' WHERE batch_id=?",(bid,))
  args=self.server.proc.args;self.server.proc.terminate();self.server.proc.wait(timeout=5)
  env=dict(os.environ,STUDIO_PASSWORD='test-only-password',STUDIO_USERNAME='admin',STUDIO_DATA=str(self.server.root/'data'),STUDIO_EXPORTS=str(self.server.root/'exports'),PORT='18773',HOST='127.0.0.1',GITHUB_BACKUP_TOKEN='',RENDER='')
  self.server.proc=subprocess.Popen(args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  for _ in range(100):
   try:
    with urlopen(self.server.base+'/health',timeout=.5):break
   except OSError:time.sleep(.03)
  self.admin=Client(self.server.base);restored=self.admin.call('/api/parquet/import/status?batch_id='+bid)['run'];self.assertEqual(restored['state'],'paused');self.assertEqual(restored['processed'],paused['processed']);self.assertFalse(restored['file_available'])
  key=self.upload(data,'resume.parquet');resumed=self.admin.call('/api/parquet/import/start',{'upload_id':key,'text_column':'Comment','import_batch_id':uuid.uuid4().hex})['run'];self.assertEqual(resumed['batch_id'],bid)
  done=self.wait(bid,{'done'});self.assertEqual(done['added'],30001);self.assertEqual(done['processed'],30001);self.assertEqual(done['duplicates'],0)
 def test_table_paging_and_member_restrictions(self):
  data=self.file(['abc'],{f'column{i}':['v'] for i in range(25)});key=self.upload(data)
  page=self.admin.call('/api/parquet/table',{'upload_id':key,'column_offset':20});self.assertEqual(len(page['columns']),7)
  account=self.admin.call('/api/admin/users',{'username':'native'+uuid.uuid4().hex[:8],'display_name':'Member'});member=Client(self.server.base,account['user']['username'],account['login_code'])
  for path,body in [('/api/parquet/import/start',{'upload_id':key,'text_column':'Comment'}),('/api/parquet/table',{'upload_id':key})]:
   with self.assertRaises(HTTPError) as ctx:member.call(path,body)
   self.assertEqual(ctx.exception.code,403)
  with self.assertRaises(HTTPError) as ctx:member.call('/api/parquet/import/status')
  self.assertEqual(ctx.exception.code,403)

if __name__=='__main__':unittest.main(verbosity=2)
