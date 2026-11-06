import base64, importlib.util, json, os, sqlite3, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

spec=importlib.util.spec_from_file_location('studio',Path(__file__).with_name('app.py'));app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class ImportTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();app.DATA=Path(self.temp.name);app.EXPORTS=app.DATA/'exports';app.init()
 def tearDown(self):self.temp.cleanup()
 def rule(self):return dict(name='Cờ bạc',category='co_bac',kind='exact',config={'pattern':'Vào nhóm cá cược kiếm tiền'},tests=[],status='active',source_sample_id=999)
 def test_preview_import_deduplicate_roundtrip_and_persist(self):
  payload={'rules':[self.rule(),self.rule()],'reviewer':'An','preview':True}
  with app.connect() as c:
   self.assertEqual(app.import_blacklist(c,payload)['duplicates'],1)
   self.assertEqual(app.state(c)['rules'],[])
  payload['preview']=False
  with app.connect() as c:self.assertEqual(app.import_blacklist(c,payload)['added'],1)
  app.init()
  with app.connect() as c:
   rules=app.state(c)['rules'];self.assertEqual(len(rules),1);self.assertEqual(rules[0]['status'],'draft');self.assertIsNone(rules[0]['source_sample_id'])
   app.export_all(c)
   exported=json.loads((app.EXPORTS/'blacklist_drafts.json').read_text())
   self.assertEqual(app.import_blacklist(c,dict(payload,rules=exported['rules']))['added'],0)
   self.assertEqual(json.loads((app.EXPORTS/'blacklist.json').read_text())['rules'],[])
 def test_invalid_batch_rolls_back(self):
  with self.assertRaises(ValueError):
   with app.connect() as c:app.import_blacklist(c,{'rules':[self.rule(),dict(self.rule(),category='invalid')],'reviewer':'An','preview':False})
  with app.connect() as c:self.assertEqual(app.state(c)['rules'],[])

class AuthTests(unittest.TestCase):
 def test_protected_routes(self):
  from http_test_support import Server,Client
  server=Server(18766)
  try:
   with urlopen(server.base+'/') as r:self.assertEqual(r.status,200)
   for path in ['/api/state','/api/session','/export/backup.sql']:
    with self.assertRaises(HTTPError) as ctx:urlopen(server.base+path)
    self.assertEqual(ctx.exception.code,401)
   admin=Client(server.base)
   self.assertEqual(admin.call('/api/session')['user']['role'],'admin')
   self.assertEqual(admin.call('/api/blacklist/import',{'rules':[ImportTests.rule(self)],'preview':False})['added'],1)
   with self.assertRaises(HTTPError) as ctx:admin.call('/api/backup/sync',{},csrf=False)
   self.assertEqual(ctx.exception.code,400)
   with self.assertRaises(HTTPError) as ctx:
    urlopen(Request(server.base+'/api/state',headers={'Authorization':'Basic '+base64.b64encode(b'admin:test-only-password').decode()}))
   self.assertEqual(ctx.exception.code,401)
  finally:server.close()

if __name__=='__main__':unittest.main()
