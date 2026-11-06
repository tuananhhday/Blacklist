"""Native Parquet fixtures; no uploaded/customer data is committed to Git."""
import io,json,os,tempfile,unittest,uuid
from pathlib import Path
from urllib.request import Request
from urllib.error import HTTPError
import pyarrow as pa
import pyarrow.parquet as pq
from parquet_import import ParquetUploads,UploadConflict,UploadExpired,CHUNK_BYTES
from http_test_support import Server,Client

class ParquetNative(unittest.TestCase):
 def setUp(self):self.uploads=ParquetUploads()
 def tearDown(self):
  for key in list(self.uploads.jobs):self.uploads.remove(key)
 def fixture(self,compression='snappy'):
  sink=pa.BufferOutputStream();pq.write_table(pa.table({'Review':['Xin chào Việt Nam',None,'', 'a'*20001,'Nội dung tiếp theo'],'context':['','','','','Ngữ cảnh'],'label':[1,0,0,1,2]}),sink,compression=compression,row_group_size=2)
  return sink.getvalue().to_pybytes()
 def upload(self,data):
  result=self.uploads.start(1,{'name':'train.parquet','size':len(data)});key=result['upload_id']
  for offset in range(0,len(data),CHUNK_BYTES):self.uploads.append(key,1,offset,data[offset:offset+CHUNK_BYTES])
  return key
 def test_snappy_zstd_mapping_skips_and_retry(self):
  for compression in ['snappy','zstd','gzip']:
   key=self.upload(self.fixture(compression));meta=self.uploads.get(key,1)['metadata'];self.assertEqual(meta['suggested_text_column'],'Review');self.assertEqual(meta['rows'],5)
   preview=self.uploads.preview(key,1,{'text_column':'Review','context_column':'context','start':0,'count':5});self.assertEqual(preview['preview'][0]['sample']['text'],'Xin chào Việt Nam')
   batch=self.uploads.batch(key,1,{'offset':0,'limit':50});self.assertEqual(len(batch['rows']),2);self.assertEqual(batch['skipped_empty'],2);self.assertEqual(batch['skipped_too_long'],1);self.assertTrue(batch['done']);self.assertNotIn('label',batch['rows'][0])
   self.assertEqual(batch,self.uploads.batch(key,1,{'offset':0,'limit':50}))
 def test_upload_validation_permissions_and_schema(self):
  data=self.fixture();started=self.uploads.start(1,{'name':'x.pq','size':len(data)});key=started['upload_id'];head=data[:20]
  self.uploads.append(key,1,0,head);self.assertEqual(self.uploads.append(key,1,0,head)['offset'],20)
  with self.assertRaises(UploadConflict):self.uploads.append(key,1,0,b'x'*20)
  with self.assertRaises(UploadExpired):self.uploads.get(key,2)
  with self.assertRaises(ValueError):self.uploads.start(1,{'name':'bad.parquet','size':300*1024*1024})
  with self.assertRaises(ValueError):self.uploads.append(key,1,20,b'x'*(CHUNK_BYTES+1))
  key=self.upload(data)
  with self.assertRaises(ValueError):self.uploads.preview(key,1,{'text_column':'missing','start':0,'count':5})
  with self.assertRaises(ValueError):self.uploads.preview(key,1,{'text_column':'label','start':0,'count':1})
  key=self.uploads.start(1,{'name':'corrupt.parquet','size':30})['upload_id']
  with self.assertRaises(ValueError):self.uploads.append(key,1,0,b'x'*30)

class ParquetHTTP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.server=Server(18769)
 @classmethod
 def tearDownClass(cls):cls.server.close()
 def setUp(self):self.admin=Client(self.server.base)
 def binary(self,client,key,offset,data,csrf=True):
  headers={'Content-Type':'application/octet-stream'}
  if csrf:headers['X-Studio-Token']=client.token
  with client.opener.open(Request(self.server.base+'/api/parquet/chunk?upload_id='+key+'&offset='+str(offset),data=data,headers=headers),timeout=30) as response:return json.load(response)
 def test_large_file_selected_window_and_existing_dedup_import(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'train-00000-of-00001.parquet'
   values=['row '+str(i)+' '+('x'*5000) for i in range(8192)]
   table=pa.table({'Review':values,'label':list(range(8192))});pq.write_table(table,path,compression=None,use_dictionary=False,row_group_size=1024)
   del values,table
   self.assertGreater(path.stat().st_size,32*1024*1024)
   start=self.admin.call('/api/parquet/start',{'name':path.name,'size':path.stat().st_size});key=start['upload_id']
   with path.open('rb') as file:
    offset=0
    while True:
     block=file.read(start['chunk_bytes'])
     if not block:break
     result=self.binary(self.admin,key,offset,block);offset=result['offset']
   self.assertEqual(result['metadata']['rows'],8192)
   preview=self.admin.call('/api/parquet/preview',{'upload_id':key,'text_column':'Review','start':4096,'count':2})
   self.assertTrue(preview['preview'][0]['sample']['text'].startswith('row 4096 '))
   batch=self.admin.call('/api/parquet/rows',{'upload_id':key,'offset':4096,'limit':50});self.assertEqual(len(batch['rows']),2)
   operation=uuid.uuid4().hex;body={'rows':batch['rows'],'operation_id':operation}
   self.assertEqual(self.admin.call('/api/import',body)['added'],2);self.assertEqual(self.admin.call('/api/import',body)['added'],2)
   self.assertEqual(self.admin.call('/api/import',{'rows':batch['rows']})['duplicates'],2)
   self.assertEqual(self.admin.call('/api/parquet/rows',{'upload_id':key,'offset':4096,'limit':50})['next_offset'],4098)
   self.admin.call('/api/parquet/close',{'upload_id':key})
 def test_admin_and_csrf_required_for_binary_and_json(self):
  user=self.admin.call('/api/admin/users',{'username':'parquet'+uuid.uuid4().hex[:8],'display_name':'Parquet member'});member=Client(self.server.base,user['user']['username'],user['login_code'])
  for call in [lambda:member.call('/api/parquet/start',{'name':'x.parquet','size':30}),lambda:self.binary(member,'x'*32,0,b'x'*30)]:
   with self.assertRaises(HTTPError) as ctx:call()
   self.assertEqual(ctx.exception.code,403)
  start=self.admin.call('/api/parquet/start',{'name':'x.parquet','size':30})
  with self.assertRaises(HTTPError) as ctx:self.binary(self.admin,start['upload_id'],0,b'x'*30,csrf=False)
  self.assertEqual(ctx.exception.code,400)

if __name__=='__main__':unittest.main(verbosity=2)
