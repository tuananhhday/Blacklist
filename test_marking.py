"""Literal teaching evidence and conservative custom context, no customer data."""
import copy,json,sqlite3,unittest,uuid
from urllib.error import HTTPError
from urllib.request import urlopen
import context_rules as rules
import blacklist_store as store
from http_test_support import Server,Client

class TeachingMarks(unittest.TestCase):
 def test_migrate_existing_examples_twice_without_data_loss(self):
  c=sqlite3.connect(':memory:')
  old=store.SCHEMA.replace(" annotation_json TEXT NOT NULL DEFAULT '{}',\n",'')
  c.executescript(old)
  c.execute("INSERT INTO studio_blacklist_examples(id,item_id,text,expected,role,source_kind,created_at) VALUES(7,1,'Câu cũ','MATCH','violation','manual','now')")
  store.migrate(c);store.migrate(c)
  self.assertEqual(c.execute('SELECT text,annotation_json FROM studio_blacklist_examples WHERE id=7').fetchone(),('Câu cũ','{}'))
 def test_marks_use_literal_unicode_offsets_and_reject_stale_or_overlapping(self):
  text='🙂 Vào nhóm cá cược.'
  a=text.index('cá');mark={'start':a,'end':a+7,'text':'cá cược','role':'topic'}
  self.assertEqual(rules.validate_annotation({'case':'invite','marks':[mark]},text)['marks'][0],mark)
  for raw in [{'case':[]},{'marks':[{**mark,'start':True}]},{'marks':[{**mark,'text':'khác'}]},{'marks':[mark,{**mark,'role':'action'}]}]:
   with self.assertRaises(ValueError):rules.validate_annotation(raw,text)

class MarkingHTTP(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.server=Server(18779)
 @classmethod
 def tearDownClass(cls):cls.server.close()
 def test_roundtrip_custom_caution_live_pin_and_export(self):
  for path in ['/phrase_marker.js','/phrase_marker.css','/sandbox/phrase_marker.js','/sandbox/phrase_marker.css']:
   with urlopen(self.server.base+path) as response:self.assertEqual(response.status,200)
  c=Client(self.server.base);text='🙂 Vào nhóm cá cược nhận thưởng.';a=text.index('cá')
  item={'name':'Dấu chữ '+uuid.uuid4().hex,'category':'co_bac','mode':'block','status':'published','match_type':'combined','config':{'topics':['cá cược'],'actions':['vào nhóm'],'cautions':['lùi lại']},'examples':[
   {'text':text,'expected':'MATCH','role':'violation','annotation':{'case':'invite','marks':[{'start':a,'end':a+7,'role':'topic','text':'cá cược'}]}},
   {'text':'Chúc bạn vui vẻ.','expected':'NO_MATCH','role':'counterexample','annotation':{'case':'neutral','marks':[]}},
   {'text':'Lùi lại: vào nhóm cá cược.','expected':'REVIEW','role':'counterexample','annotation':{'case':'warning','marks':[{'start':0,'end':7,'text':'Lùi lại','role':'caution'}]}}
  ]}
  saved=c.call('/api/studio/item',item)['item'];self.assertEqual(saved['examples'][0]['annotation'],item['examples'][0]['annotation'])
  result=c.call('/api/studio/demo',{'text':'Lùi lại: vào nhóm cá cược.'});self.assertEqual(result['decision'],'REVIEW');self.assertIn('custom_caution',result['matches'][0]['ambiguities'])
  self.assertEqual(c.call('/api/studio/demo',{'text':'Lùi lại.'})['decision'],'NO_MATCH')
  self.assertEqual(c.call('/api/studio/demo',{'text':text})['decision'],'BLOCK')
  changed=copy.deepcopy(saved);changed['status']='draft';changed['config']['cautions']=['nhận thưởng']
  c.call('/api/studio/item',changed);self.assertEqual(c.call('/api/studio/demo',{'text':text})['decision'],'BLOCK')
  pack=c.call('/export/blacklist_pack.json');live=next(x for x in pack['published_items'] if x['id']==saved['id']);self.assertEqual(live['config']['cautions'],['lùi lại']);self.assertEqual(live['examples'][0]['annotation'],item['examples'][0]['annotation'])
  invalid=copy.deepcopy(item);invalid['examples'][0]['annotation']['marks'][0]['text']='không nguyên văn'
  with self.assertRaises(HTTPError) as err:c.call('/api/studio/item',invalid)
  self.assertEqual(err.exception.code,400)

if __name__=='__main__':unittest.main()
