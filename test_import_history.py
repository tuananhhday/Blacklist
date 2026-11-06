import unittest,uuid
from urllib.error import HTTPError
from http_test_support import Server,Client

class ReversibleImports(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.server=Server(18771)
 @classmethod
 def tearDownClass(cls):cls.server.close()
 def setUp(self):self.admin=Client(self.server.base)
 def row(self,text):return {'text':text,'source':'undo-test','synthetic':True}
 def error(self,status,fn):
  with self.assertRaises(HTTPError) as caught:fn()
  self.assertEqual(caught.exception.code,status)
 def test_undo_restore_only_new_rows_and_preserve_manual_deletions(self):
  marker=uuid.uuid4().hex;old=marker+' existing';self.admin.call('/api/import',{'rows':[self.row(old)]})
  bid=uuid.uuid4().hex;operation=uuid.uuid4().hex
  body={'rows':[self.row(old),self.row(marker+' new 1'),self.row(marker+' new 2')],'import_batch_id':bid,'import_name':'train.parquet · test','operation_id':operation}
  first=self.admin.call('/api/import',body);self.assertEqual(first['added'],2);self.assertEqual(first['duplicates'],1);self.admin.call('/api/import',body)
  self.admin.call('/api/import',{'rows':[self.row(marker+' new 3')],'import_batch_id':bid,'import_name':'train.parquet · test'})
  batch=next(b for b in self.admin.call('/api/admin/imports')['batches'] if b['id']==bid);self.assertEqual(batch['added'],3);self.assertEqual(batch['duplicates'],1)
  samples=self.admin.call('/api/admin/samples?batch_id='+bid)['samples'];self.assertEqual(len(samples),3);self.assertNotIn(old,{s['text'] for s in samples})
  edited=samples[0];self.admin.call('/api/admin/samples/edit',{'sample_id':edited['id'],'text':edited['text']+' sửa lại','context':'','source':'undo-test','synthetic':True})
  manually=samples[1];self.admin.call('/api/admin/samples/delete',{'sample_id':manually['id']})
  undone=self.admin.call('/api/admin/imports/undo',{'batch_id':bid});self.assertEqual(undone['changed'],2)
  texts={s['text'] for s in self.admin.call('/api/state')['samples']};self.assertIn(old,texts);self.assertNotIn(edited['text']+' sửa lại',texts)
  restored=self.admin.call('/api/admin/imports/restore',{'batch_id':bid});self.assertEqual(restored['changed'],2)
  active={s['id'] for s in self.admin.call('/api/state')['samples']};self.assertIn(edited['id'],active);self.assertNotIn(manually['id'],active)
  duplicate_bid=self.admin.call('/api/import',{'rows':[self.row(old)]})['import_batch_id'];self.assertEqual(self.admin.call('/api/admin/imports/undo',{'batch_id':duplicate_bid})['changed'],0);self.assertIn(old,{s['text'] for s in self.admin.call('/api/state')['samples']})
 def test_permissions_live_claims_and_history_are_preserved(self):
  account=self.admin.call('/api/admin/users',{'username':'undo'+uuid.uuid4().hex[:8],'display_name':'Undo member'});member=Client(self.server.base,account['user']['username'],account['login_code'])
  added=self.admin.call('/api/import',{'rows':[self.row('undo '+uuid.uuid4().hex)]});bid=added['import_batch_id'];sample=self.admin.call('/api/admin/samples?batch_id='+bid)['samples'][0];sid=sample['id']
  self.admin.call('/api/admin/assign',{'plan':[{'user_id':member.user['id'],'sample_ids':[sid]}]});member.call('/api/work/claim',{'sample_id':sid})
  self.error(403,lambda:member.call('/api/admin/imports/undo',{'batch_id':bid}));self.error(409,lambda:self.admin.call('/api/admin/imports/undo',{'batch_id':bid}))
  labels={k:None for k in member.call('/api/state')['categories']};labels['spam']=1
  review=member.call('/api/review',{'sample_id':sid,'base_revision':0,'labels':labels,'decision':'VIOLATION','reason':'test undo','active':True})
  replacement=self.admin.call('/api/admin/samples/edit',{'sample_id':sid,'text':sample['text']+' bản thay thế','context':'','source':'undo-test','synthetic':True})['replacement_sample_id']
  self.assertEqual(self.admin.call('/api/admin/imports/undo',{'batch_id':bid})['changed'],1)
  self.assertEqual(self.admin.call('/api/admin/review?id='+str(review['review_id']))['sample']['text'],sample['text'])
  self.admin.call('/api/admin/imports/restore',{'batch_id':bid});active={s['id'] for s in member.call('/api/state')['samples']};self.assertIn(replacement,active);self.assertNotIn(sid,active)
 def test_active_blacklist_blocks_bulk_undo(self):
  added=self.admin.call('/api/import',{'rows':[self.row('active-rule '+uuid.uuid4().hex)]});bid=added['import_batch_id'];sample=self.admin.call('/api/admin/samples?batch_id='+bid)['samples'][0]
  rule={'name':'test active','category':'spam','kind':'exact','config':{'pattern':sample['text']},'tests':[{'text':sample['text'],'expected':'MATCH'},{'text':'câu đối chiếu','expected':'NO_MATCH'}],'status':'active','reason':'test','source_sample_id':sample['id']}
  saved=self.admin.call('/api/rule',rule);self.error(409,lambda:self.admin.call('/api/admin/imports/undo',{'batch_id':bid}))
  self.admin.call('/api/rule',dict(rule,id=saved['id'],version=saved['version'],status='disabled'));self.assertEqual(self.admin.call('/api/admin/imports/undo',{'batch_id':bid})['changed'],1)

if __name__=='__main__':unittest.main(verbosity=2)
