import json,sqlite3,unittest,uuid
from urllib.error import HTTPError
from http_test_support import Server,Client

class BlacklistWorkflow(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.server=Server(18774)
 @classmethod
 def tearDownClass(cls):cls.server.close()
 def setUp(self):
  self.admin=Client(self.server.base)
  account=self.admin.call('/api/admin/users',{'username':'bl'+uuid.uuid4().hex[:10],'display_name':'Người gán nhãn'})
  self.member=Client(self.server.base,account['user']['username'],account['login_code'])
  text='Nội dung '+uuid.uuid4().hex+' mời gọi vào nhóm cá cược.'
  result=self.admin.call('/api/import',{'rows':[{'text':text,'context':'Nguồn kiểm thử','source':'test','synthetic':True}]})
  self.sample=self.admin.call('/api/admin/samples?batch_id='+result['import_batch_id'])['samples'][0]
  self.admin.call('/api/admin/assign',{'plan':[{'user_id':self.member.user['id'],'sample_ids':[self.sample['id']]}]})
 def labels(self,positive=True):
  values={k:None for k in self.member.call('/api/state')['categories']};values['spam']=1 if positive else 0;return values
 def review(self,send=False,base=0,decision='VIOLATION',**extra):
  self.member.call('/api/work/claim',{'sample_id':self.sample['id']})
  return self.member.call('/api/review',dict(sample_id=self.sample['id'],base_revision=base,labels=self.labels(decision=='VIOLATION'),decision=decision,propose_rule=send,**extra))
 def error(self,status,fn):
  with self.assertRaises(HTTPError) as caught:fn()
  self.assertEqual(caught.exception.code,status)
 def test_labels_only_then_propose_without_extra_review_or_duplicates(self):
  saved=self.review();self.assertEqual(self.member.call('/api/state')['rules'],[])
  payload={'sample_id':self.sample['id'],'review_id':saved['review_id'],'candidate_evidence':'vào nhóm cá cược'}
  first=self.member.call('/api/blacklist/propose',payload);self.assertEqual(len(first['proposals']),1);self.assertTrue(first['proposals'][0]['created'])
  second=self.member.call('/api/blacklist/propose',payload);self.assertFalse(second['proposals'][0]['created']);self.assertEqual(first['proposals'][0]['id'],second['proposals'][0]['id'])
  with sqlite3.connect(self.server.root/'data/studio.sqlite3') as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM reviews WHERE sample_id=?',(self.sample['id'],)).fetchone()[0],1)
  rule=self.member.call('/api/state')['rules'][0];self.assertEqual(rule['status'],'draft');self.assertEqual(rule['source_review_id'],saved['review_id']);self.assertEqual(rule['evidence'],'vào nhóm cá cược');self.assertEqual(rule['source_text'],self.sample['text']);self.assertEqual(rule['source_context'],'Nguồn kiểm thử');self.assertEqual(rule['source_labels']['spam'],1);self.assertEqual(rule['config']['pattern'],self.sample['text'])
  row=dict(rule,name='Nháp đã làm rõ',intent='Mời gọi / quảng bá',evidence='mời gọi vào nhóm',reason='Dấu hiệu mời tham gia trong câu nguồn.')
  result=self.member.call('/api/rule',row);updated=self.member.call('/api/state')['rules'][0];self.assertEqual(updated['intent'],'Mời gọi / quảng bá');self.assertEqual(updated['evidence'],'mời gọi vào nhóm');self.assertEqual(updated['source_review_id'],saved['review_id'])
  self.error(400,lambda:self.member.call('/api/rule',dict(updated,evidence='Đoạn không nằm trong câu nguồn')))
  self.error(403,lambda:self.member.call('/api/rule',dict(updated,status='active')))
 def test_save_and_send_is_atomic_and_idempotent(self):
  op=uuid.uuid4().hex;first=self.review(True,candidate_evidence='cá cược',operation_id=op)
  self.assertTrue(first['proposals']);self.assertEqual(self.member.call('/api/state')['samples'][0]['review']['revision'],1)
  self.member.call('/api/work/claim',{'sample_id':self.sample['id']})
  again=self.member.call('/api/review',{'sample_id':self.sample['id'],'base_revision':0,'labels':self.labels(),'decision':'VIOLATION','propose_rule':True,'candidate_evidence':'cá cược','operation_id':op})
  self.assertEqual(first['proposals'],again['proposals']);self.assertEqual(len(self.member.call('/api/state')['rules']),1)
 def test_invalid_excerpt_cannot_create_review_or_rule(self):
  self.error(400,lambda:self.review(True,candidate_evidence='bằng chứng bịa'))
  state=self.member.call('/api/state');self.assertIsNone(state['samples'][0]['review']);self.assertEqual(state['rules'],[])
 def test_member_scope_and_stale_source(self):
  saved=self.review(True,candidate_evidence='cá cược');rule=self.member.call('/api/state')['rules'][0]
  stranger=self.admin.call('/api/admin/users',{'username':'stranger'+uuid.uuid4().hex[:6],'display_name':'Khác'});other=Client(self.server.base,stranger['user']['username'],stranger['login_code'])
  self.error(403,lambda:other.call('/api/blacklist/propose',{'sample_id':self.sample['id'],'candidate_evidence':'cá cược'}))
  self.review(base=1,decision='ALLOW')
  self.assertTrue(self.member.call('/api/state')['rules'][0]['source_stale'])
  self.error(400,lambda:self.member.call('/api/blacklist/propose',{'sample_id':self.sample['id'],'review_id':saved['review_id']}))
  self.error(400,lambda:self.admin.call('/api/rule',dict(rule,status='active',tests=[{'text':self.sample['text'],'expected':'MATCH'},{'text':'Câu đối chiếu','expected':'NO_MATCH'}])))
 def test_export_import_preserves_metadata_but_not_foreign_review_links(self):
  self.review(True,candidate_evidence='cá cược',intent='Mời gọi / quảng bá');rule=self.member.call('/api/state')['rules'][0]
  self.assertEqual(rule['intent'],'Mời gọi / quảng bá')
  # A different pattern makes this an actual import rather than a duplicate existing rule.
  copied=dict(rule,config={'pattern':'Mẫu khác để nhập'},name='Nguồn từ file')
  self.admin.call('/api/blacklist/import',{'rules':[copied],'preview':False})
  restored=next(r for r in self.admin.call('/api/state')['rules'] if r['name']=='Nguồn từ file');self.assertEqual(restored['intent'],copied['intent']);self.assertEqual(restored['evidence'],copied['evidence']);self.assertEqual(restored['source_text'],copied['source_text']);self.assertIsNone(restored['source_review_id']);self.assertIsNone(restored['source_sample_id'])

if __name__=='__main__':unittest.main(verbosity=2)
