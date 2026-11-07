"""Integration checks: temporary database only, never modifies user data."""
import json, os, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

class Workflow(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from http_test_support import Server,Client
  cls.server=Server(18765);cls.root=cls.server.root;cls.base=cls.server.base;cls.client=Client(cls.base)
 @classmethod
 def tearDownClass(cls):cls.server.close()
 def call(self,path,data=None,token=True):return self.client.call(path,data,csrf=token)
 def download(self,name):
  with self.client.opener.open(self.base+'/export/'+name) as response:return response.read().decode()
 def test_workflow(self):
  self.assertEqual(self.call('/api/state')['samples'],[])
  rows=[{'text':'Vào nhóm cá cược kiếm tiền','source':'test','synthetic':True}]
  self.assertEqual(self.call('/api/import',{'rows':rows})['added'],1)
  self.assertEqual(self.call('/api/import',{'rows':rows})['duplicates'],1)
  state=self.call('/api/state');sample=state['samples'][0];labels={k:None for k in state['categories']};labels['co_bac']=1
  review=dict(operation_id='c'*32,sample_id=sample['id'],base_revision=0,decision='VIOLATION',labels=labels,intent='Mời gọi',evidence='Vào nhóm',reason='Mời tham gia',reviewer='test')
  self.call('/api/work/claim',{'sample_id':sample['id'],'reviewer':'test'})
  self.call('/api/review',review)
  self.call('/api/work/claim',{'sample_id':sample['id'],'reviewer':'test'})
  self.assertTrue(self.call('/api/review',review)['saved'])
  self.assertEqual(self.call('/api/state')['claims'],[])
  with self.assertRaises(HTTPError):self.call('/api/review',dict(review,operation_id='d'*32))
  data=[json.loads(x) for x in self.download('training_data.jsonl').splitlines()];self.assertEqual(data[0]['labels']['spam'],None);self.assertEqual(data[0]['label_mask']['spam'],0)
  rule=dict(name='Luật thử',category='co_bac',kind='combined',config={'topic':['cá cược'],'behavior':['vào nhóm'],'context':['không nên']},tests=[{'text':rows[0]['text'],'expected':'MATCH'},{'text':'Không nên vào nhóm cá cược','expected':'CONTEXT_REVIEW'},{'text':'Vào nhóm học','expected':'NO_MATCH'}],status='draft',reviewer='test',reason='Chỉ để kiểm tra',source_sample_id=sample['id'])
  d=self.call('/api/rule',rule);self.assertEqual(json.loads(self.download('blacklist.json'))['rules'],[])
  rule.update(id=d['id'],version=d['version'],status='active');d=self.call('/api/rule',rule)
  out=json.loads(self.download('blacklist.json'));self.assertEqual(len(out['rules']),1)
  probe=self.call('/api/test',{'rule':rule,'text':'Không nên vào nhóm cá cược'});self.assertEqual(probe['probe']['result'],'CONTEXT_REVIEW')
  rule.update(version=d['version'],status='disabled');self.call('/api/rule',rule)
  self.assertEqual(json.loads(self.download('blacklist.json'))['rules'],[])
  self.assertEqual(len(self.call('/api/history')['rules']),3)
  import sqlite3
  restored=sqlite3.connect(':memory:');restored.executescript(self.download('backup.sql'));self.assertEqual(restored.execute('select count(*) from reviews').fetchone()[0],1);restored.close()
  with self.assertRaises(HTTPError):self.call('/api/import',{'rows':rows},token=False)
  for path in ['/', '/app.js','/style.css']:
   with urlopen(self.base+path) as r:self.assertEqual(r.status,200)

if __name__=='__main__':unittest.main(verbosity=2)
