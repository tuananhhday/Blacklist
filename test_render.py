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
  with tempfile.TemporaryDirectory() as d:
   env=dict(os.environ,STUDIO_PASSWORD='test-only-password',STUDIO_DATA=d,STUDIO_EXPORTS=d+'/exports',PORT='18766',HOST='127.0.0.1')
   proc=subprocess.Popen([sys.executable,'app.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    for _ in range(60):
     try:
      with urlopen('http://127.0.0.1:18766/health',timeout=1) as r:self.assertEqual(r.status,200)
      break
     except OSError:time.sleep(.1)
    else:self.fail('Server did not start')
    auth='Basic '+base64.b64encode(b'admin:test-only-password').decode()
    for path in ['/','/api/state','/api/session','/export/backup.sql']:
     with self.assertRaises(HTTPError) as ctx:urlopen('http://127.0.0.1:18766'+path)
     self.assertEqual(ctx.exception.code,401)
     with urlopen(Request('http://127.0.0.1:18766'+path,headers={'Authorization':auth})) as r:self.assertEqual(r.status,200)
    with urlopen(Request('http://127.0.0.1:18766/api/session',headers={'Authorization':auth})) as r:token=json.load(r)['token']
    body=json.dumps({'rules':[ImportTests.rule(self)],'preview':False,'reviewer':'An'}).encode()
    with urlopen(Request('http://127.0.0.1:18766/api/blacklist/import',data=body,headers={'Authorization':auth,'X-Studio-Token':token,'Content-Type':'application/json'})) as r:self.assertEqual(json.load(r)['added'],1)
    with self.assertRaises(HTTPError) as ctx:urlopen(Request('http://127.0.0.1:18766/api/blacklist/import',data=body,headers={'Authorization':auth,'Content-Type':'application/json'}))
    self.assertEqual(ctx.exception.code,400)
   finally:proc.terminate();proc.wait(timeout=5)

if __name__=='__main__':unittest.main()
