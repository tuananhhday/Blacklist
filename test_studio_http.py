"""Authenticated HTTP checks for curation and demo; temporary synthetic data only."""
import json,sqlite3,unittest,uuid
from urllib.error import HTTPError
from urllib.request import urlopen
from http_test_support import Server,Client


class StudioHTTP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.server=Server(18776)
 @classmethod
 def tearDownClass(cls):cls.server.close()
 def setUp(self):
  self.tag=uuid.uuid4().hex[:10];self.admin=Client(self.server.base)
  def member(prefix):
   record=self.admin.call('/api/admin/users',{'username':prefix+self.tag,'display_name':prefix+' kiểm thử'})
   return Client(self.server.base,record['user']['username'],record['login_code'])
  self.member=member('studio');self.other=member('other')
  self.topic='cá cược '+self.tag
  self.invitation='Vào nhóm '+self.topic+' đăng ký nhận thưởng.'
  self.counterexample='Bình luận học tập thông thường '+self.tag+'.'
  self.foreign='Vào nhóm '+self.topic+' phiên riêng tư của người khác.'
  result=self.admin.call('/api/import',{'rows':[{'text':text,'context':'Ngữ cảnh nguồn riêng '+self.tag,'source':'Nguồn kiểm thử riêng '+self.tag,'synthetic':True} for text in [self.invitation,self.counterexample,self.foreign]]})
  self.samples=self.admin.call('/api/admin/samples?batch_id='+result['import_batch_id'])['samples']
  self.by_text={sample['text']:sample for sample in self.samples}
  self.positive=self.by_text[self.invitation];self.negative=self.by_text[self.counterexample];self.foreign_sample=self.by_text[self.foreign]
  self.admin.call('/api/admin/assign',{'plan':[{'user_id':self.member.user['id'],'sample_ids':[self.positive['id'],self.negative['id']]},{'user_id':self.other.user['id'],'sample_ids':[self.foreign_sample['id']]}]})
  self.positive_review=self.review(self.member,self.positive,'VIOLATION')
  self.negative_review=self.review(self.member,self.negative,'ALLOW')
  self.foreign_review=self.review(self.other,self.foreign_sample,'VIOLATION')
 def review(self,client,sample,decision,base=0,**extra):
  client.call('/api/work/claim',{'sample_id':sample['id']})
  labels={k:None for k in client.call('/api/state')['categories']};labels['co_bac']=1 if decision=='VIOLATION' else 0
  return client.call('/api/review',dict(sample_id=sample['id'],base_revision=base,decision=decision,labels=labels,**extra))
 def definition(self,**changes):
  item={'name':'Cờ bạc · Mời gọi '+self.tag,'category':'co_bac','status':'draft','mode':'signal','match_type':'combined','config':{'topics':[self.topic],'actions':['vào nhóm'],'pattern':''},'examples':[
   {'text':self.invitation,'context':self.positive['context'],'role':'violation','expected':'MATCH','source_sample_id':self.positive['id'],'source_review_id':self.positive_review['review_id']},
   {'text':self.counterexample,'context':self.negative['context'],'role':'counterexample','expected':'NO_MATCH','source_sample_id':self.negative['id'],'source_review_id':self.negative_review['review_id']}
  ]}
  item.update(changes);return item
 def error(self,status,fn):
  with self.assertRaises(HTTPError) as caught:fn()
  self.assertEqual(caught.exception.code,status)
  return json.loads(caught.exception.read())
 def save(self,client=None,**changes):return (client or self.admin).call('/api/studio/item',self.definition(**changes))['item']
 def update(self,item,client=None,**changes):return (client or self.admin).call('/api/studio/item',dict(item,**changes))['item']
 def demo(self,text=None,client=None):return (client or self.admin).call('/api/studio/demo',{'text':text or self.invitation,'context':''})
 def test_static_auth_and_csrf_boundaries(self):
  for path in ['/demo','/studio.js','/studio.css','/sandbox/','/sandbox/app.js','/sandbox/engine.js','/sandbox/style.css']:
   with urlopen(self.server.base+path) as response:self.assertEqual(response.status,200)
  for path in ['/api/studio/items','/api/studio/sources','/export/blacklist_pack.json']:
   self.error(401,lambda path=path:urlopen(self.server.base+path))
  self.error(400,lambda:self.admin.call('/api/studio/item',self.definition(),csrf=False))
  self.error(400,lambda:self.admin.call('/api/studio/demo',{'text':self.invitation},csrf=False))
  self.error(403,lambda:self.member.call('/api/studio/import',{'items':[self.definition()]}))
 def test_draft_preview_is_separate_from_runtime_and_published_tests(self):
  item=self.save()
  preview=self.admin.call('/api/studio/preview',{'item':dict(item,mode='block'),'text':self.invitation,'context':''})
  self.assertTrue(preview['preview']);self.assertTrue(preview['tests']);self.assertTrue(all(row['passed'] for row in preview['tests']))
  self.assertEqual(preview['result']['decision'],'BLOCK')
  self.assertEqual(self.demo()['decision'],'NO_MATCH')
  item=self.update(item,status='published',mode='block')
  result=self.demo();self.assertEqual(result['decision'],'BLOCK');self.assertTrue(any(hit['rule_id']==item['id'] for hit in result['matches']))
  self.assertEqual(self.demo('Đừng vào nhóm '+self.topic+', dễ mất tiền.')['decision'],'REVIEW')
  harmless=self.demo(self.counterexample);self.assertEqual(harmless['decision'],'NO_MATCH');self.assertNotEqual(harmless['decision'],'ALLOW')
  item=self.update(item,status='disabled')
  self.assertEqual(self.demo()['decision'],'NO_MATCH')
  history=self.admin.call('/api/studio/history?id='+str(item['id']))['history'];self.assertGreaterEqual(len(history),3)
 def test_member_draft_scope_and_admin_publication(self):
  item=self.save(self.member)
  self.assertEqual(item['status'],'draft')
  self.error(403,lambda:self.update(item,self.member,status='published',mode='block'))
  self.error(403,lambda:self.other.call('/api/studio/item?id='+str(item['id'])))
  self.error(403,lambda:self.other.call('/api/studio/history?id='+str(item['id'])))
  self.error(403,lambda:self.update(item,self.other,name='Không được sửa'))
  member_sources=self.member.call('/api/studio/sources')['sources']
  source_ids={row['id'] if 'id' in row else row['sample_id'] for row in member_sources}
  self.assertIn(self.positive['id'],source_ids);self.assertIn(self.negative['id'],source_ids);self.assertNotIn(self.foreign_sample['id'],source_ids)
  foreign_example=self.definition();foreign_example['examples'][0]={'text':self.foreign,'context':self.foreign_sample['context'],'expected':'MATCH','role':'violation','source_sample_id':self.foreign_sample['id'],'source_review_id':self.foreign_review['review_id']}
  self.error(403,lambda:self.member.call('/api/studio/item',foreign_example))
  item=self.update(item,status='published',mode='block')
  result=self.demo(client=self.other);self.assertEqual(result['decision'],'BLOCK')
  serialized=json.dumps(result,ensure_ascii=False)
  self.assertNotIn(self.positive['context'],serialized);self.assertNotIn('source_review_id',serialized);self.assertNotIn('source_sample_id',serialized);self.assertNotIn('examples',serialized)
  self.assertTrue(any(hit['rule_id']==item['id'] for hit in result['matches']))
 def test_editing_live_rule_as_draft_preserves_published_snapshot(self):
  item=self.save(status='published',mode='block');self.assertEqual(self.demo()['decision'],'BLOCK')
  changed=dict(item,status='draft',config={'topics':['chủ đề khác '+self.tag],'actions':['hành vi khác'],'pattern':''})
  edited=self.admin.call('/api/studio/item',changed)['item']
  self.assertEqual(edited['status'],'draft');self.assertTrue(edited['has_pending_changes'])
  self.assertEqual(self.demo()['decision'],'BLOCK')
  disabled=self.update(edited,status='disabled')
  self.assertEqual(self.demo()['decision'],'NO_MATCH');self.assertEqual(disabled['status'],'disabled')
  restored=self.update(disabled,status='draft')
  self.assertEqual(restored['status'],'draft');self.assertIsNone(restored['published_version'])
  self.assertEqual(self.demo()['decision'],'NO_MATCH')
 def test_conflicts_and_invalid_examples_cannot_publish(self):
  item=self.save();updated=self.update(item,name='Tên đã sửa '+self.tag)
  self.error(409,lambda:self.update(item,name='Ghi đè bản cũ'))
  invalid=dict(updated,status='published',mode='block',examples=[dict(example,expected='MATCH') for example in updated['examples']])
  self.error(400,lambda:self.admin.call('/api/studio/item',invalid))
  self.assertEqual(self.admin.call('/api/studio/item?id='+str(item['id']))['item']['status'],'draft')
 def test_bookmarks_include_allow_and_preserve_review_count(self):
  payload={'sample_id':self.negative['id'],'review_id':self.negative_review['review_id'],'marked':True}
  first=self.member.call('/api/studio/bookmark',payload);second=self.member.call('/api/studio/bookmark',payload)
  self.assertTrue(first['marked']);self.assertTrue(second['marked'])
  self.error(403,lambda:self.other.call('/api/studio/bookmark',payload))
  self.review(self.member,self.negative,'ALLOW',base=1,mark_curation=True)
  marked=self.member.call('/api/studio/sources?marked=1')['sources'];marked_ids={row['id'] if 'id' in row else row['sample_id'] for row in marked};self.assertIn(self.negative['id'],marked_ids)
  with sqlite3.connect(self.server.root/'data/studio.sqlite3') as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM reviews WHERE sample_id=?',(self.negative['id'],)).fetchone()[0],2)
 def test_stale_source_does_not_silently_keep_blocking(self):
  item=self.save(status='published',mode='block');self.assertEqual(self.demo()['decision'],'BLOCK')
  self.review(self.member,self.positive,'ALLOW',base=1)
  current=self.admin.call('/api/studio/item?id='+str(item['id']))['item'];self.assertTrue(current['source_stale'])
  result=self.demo();self.assertEqual(result['decision'],'REVIEW');self.assertTrue(result['matches'])
  # A fresh manual draft must not erase stale provenance of the pinned live
  # revision when that live revision is exported to an offline demo.
  current['status']='draft';current['examples']=[
   {'text':self.invitation,'expected':'MATCH','role':'violation'},
   {'text':self.counterexample,'expected':'NO_MATCH','role':'counterexample'}]
  updated=self.admin.call('/api/studio/item',current)['item'];self.assertFalse(updated['source_stale'])
  with self.admin.opener.open(self.server.base+'/export/blacklist_pack.json') as response:pack=json.load(response)
  live=next(row for row in pack['published_items'] if row['id']==item['id'])
  self.assertTrue(live['source_stale']);self.assertTrue(live['source_warnings']);self.assertEqual(live['mode'],'signal')
  self.assertEqual(live['configured_mode'],'block');self.assertEqual(live['published_version'],item['published_version'])
  self.assertFalse(next(row for row in pack['items'] if row['id']==item['id'])['source_stale'])
 def test_editor_drafts_are_scoped_and_bounded(self):
  key='new';payload={'category':'co_bac','unfinished_selection':'cá cược'}
  self.member.call('/api/studio/draft',{'key':key,'payload':payload})
  path='/api/studio/draft?key='+key+'&client_id='+self.member.client_id
  self.assertEqual(self.member.call(path)['draft']['payload'],payload)
  # Another actor cannot access this draft even if they know the raw client ID.
  self.assertIsNone(self.other.call(path)['draft'])
  self.error(400,lambda:self.member.call('/api/studio/draft',{'key':key,'payload':{'text':'🙂'*30000}}))
  self.assertEqual(self.member.call(path)['draft']['payload'],payload)
  self.assertTrue(self.member.call('/api/studio/draft/delete',{'key':key})['deleted'])
  self.assertIsNone(self.member.call(path)['draft'])
 def test_admin_can_disable_rule_after_source_is_archived(self):
  item=self.save(status='published',mode='block')
  self.admin.call('/api/admin/samples/delete',{'sample_id':self.positive['id']})
  result=self.demo();self.assertEqual(result['decision'],'REVIEW')
  with self.admin.opener.open(self.server.base+'/export/blacklist_pack.json') as response:pack=json.load(response)
  live=next(row for row in pack['published_items'] if row['id']==item['id'])
  self.assertTrue(live['source_stale']);self.assertEqual(live['mode'],'signal')
  self.error(409,lambda:self.update(item,status='published'))
  disabled=self.update(item,status='disabled')
  self.assertEqual(disabled['status'],'disabled');self.assertEqual(self.demo()['decision'],'NO_MATCH')
 def test_export_import_never_reactivates_foreign_source_links(self):
  item=self.save(status='published',mode='block')
  with self.admin.opener.open(self.server.base+'/export/blacklist_pack.json') as response:pack=json.load(response)
  self.assertEqual(pack['schema_version'],2)
  exported=next(row for row in pack['items'] if row['id']==item['id'])
  # Distinct config makes this a real import rather than an existing-pattern
  # duplicate. Import must still discard the foreign IDs and active mode.
  exported=dict(exported,name='Nhập từ file '+self.tag,config=dict(exported['config'],topics=exported['config']['topics']+[self.topic+' mở rộng']))
  result=self.admin.call('/api/studio/import',{'pack':{'schema_version':2,'items':[exported]}})
  self.assertGreaterEqual(result.get('added',result.get('imported',0)),1)
  items=self.admin.call('/api/studio/items?status=draft&q='+self.tag)['items'];summary=next(row for row in items if row['name']==exported['name'])
  restored=self.admin.call('/api/studio/item?id='+str(summary['id']))['item']
  self.assertEqual(restored['status'],'draft');self.assertEqual(restored['mode'],'signal')
  self.assertTrue(all(not example.get('source_sample_id') and not example.get('source_review_id') for example in restored['examples']))
  self.assertTrue(all(example['source_kind']=='imported' for example in restored['examples']))
  self.assertEqual(self.demo()['decision'],'BLOCK')


if __name__=='__main__':unittest.main(verbosity=2)
