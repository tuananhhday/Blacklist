import json,sqlite3,time,unittest,uuid
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from http_test_support import Server,Client

class WorkspaceAccounts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.server=Server(18768)
 @classmethod
 def tearDownClass(cls):cls.server.close()
 def setUp(self):self.admin=Client(self.server.base)
 def error(self,status,fn):
  with self.assertRaises(HTTPError) as ctx:fn()
  self.assertEqual(ctx.exception.code,status)
 def member(self):
  name='m'+uuid.uuid4().hex[:12]
  result=self.admin.call('/api/admin/users',{'username':name,'display_name':name,'role':'admin','operation_id':uuid.uuid4().hex})
  self.assertEqual(result['user']['role'],'member')
  with sqlite3.connect(self.server.root/'data/studio.sqlite3') as c:
   self.assertNotIn(result['login_code'],c.execute('SELECT code_hash FROM auth_users WHERE id=?',(result['user']['id'],)).fetchone()[0])
   self.assertFalse(any(result['login_code'] in r[0] for r in c.execute('SELECT result_json FROM operations')))
  return Client(self.server.base,name,result['login_code']),result
 def import_plan(self,people,count=4):
  marker=uuid.uuid4().hex
  self.admin.call('/api/import',{'rows':[{'text':marker+' câu '+str(i),'source':'test','synthetic':True} for i in range(count)]})
  plan=self.admin.call('/api/admin/assign/preview',{'user_ids':[p.user['id'] for p in people],'per_user':count//len(people)})
  return plan
 def payload(self,client,sample,**extra):
  labels={k:None for k in client.call('/api/state')['categories']};labels['spam']=1
  return dict(sample_id=sample['id'],base_revision=sample['review']['revision'] if sample['review'] else 0,decision='VIOLATION',labels=labels,reason='Kiểm thử nhãn',reviewer='admin giả mạo',active=True,operation_id=uuid.uuid4().hex,**extra)
 def test_permissions_allocation_timing_and_quality(self):
  a,created=self.member();b,_=self.member()
  for path,body in [('/api/import',{'rows':[]}),('/api/admin/users',{}),('/api/backup/sync',{})]:self.error(403,lambda path=path,body=body:a.call(path,body))
  for path in ['/api/admin/overview','/api/admin/reviews','/export/backup.sql','/api/history']:self.error(403,lambda path=path:a.call(path))
  preview=self.import_plan([a,b]);op=uuid.uuid4().hex
  first=self.admin.call('/api/admin/assign',{'plan':preview['plan'],'operation_id':op})
  self.assertEqual(first['assigned'],4)
  self.assertEqual(self.admin.call('/api/admin/assign',{'plan':preview['plan'],'operation_id':op})['assigned'],4)
  self.error(409,lambda:self.admin.call('/api/admin/assign',{'plan':preview['plan']}))
  sa=a.call('/api/state');sb=b.call('/api/state');self.assertEqual(len(sa['samples']),2);self.assertFalse({s['id'] for s in sa['samples']} & {s['id'] for s in sb['samples']})
  sid=a.call('/api/work/claim',{})['sample_id'];sample=next(s for s in sa['samples'] if s['id']==sid)
  self.error(403,lambda:b.call('/api/work/claim',{'sample_id':sid,'_user':a.user}))
  self.error(403,lambda:self.admin.call('/api/work/claim',{'sample_id':sid}))
  body=self.payload(a,sample,propose_rule=True,elapsed_ms=99999999,_received_at=1e20)
  saved=a.call('/api/review',body);rid=saved['review_id'];a.call('/api/review',body)
  state=a.call('/api/state');rule=state['rules'][0];self.assertEqual(rule['status'],'draft');self.assertEqual(rule['created_by_user_id'],a.user['id'])
  self.assertEqual(b.call('/api/state')['rules'],[])
  self.error(403,lambda:a.call('/api/rule',dict(rule,status='active',config=rule['config'],tests=rule['tests'])))
  details=self.admin.call('/api/admin/review?id='+str(rid));r=details['review'];self.assertEqual(r['user_id'],a.user['id']);self.assertEqual(r['reviewer'],a.user['display_name']);self.assertEqual(r['fast_flag'],1);self.assertLess(r['elapsed_ms'],r['threshold_ms'])
  self.admin.call('/api/admin/audit',{'review_id':rid,'verdict':'needs_fix','note':'Cần đọc lại ngữ cảnh.'})
  updated=next(s for s in a.call('/api/state')['samples'] if s['id']==sid);self.assertTrue(updated['work_pending'])
  a.call('/api/work/claim',{'sample_id':sid})
  with sqlite3.connect(self.server.root/'data/studio.sqlite3') as c:c.execute('UPDATE annotation_attempts SET started_at=? WHERE sample_id=? AND closed_at IS NULL',(time.time()-10,sid))
  second=a.call('/api/review',self.payload(a,updated,elapsed_ms=0));r2=self.admin.call('/api/admin/review?id='+str(second['review_id']))['review'];self.assertGreaterEqual(r2['elapsed_ms'],9000);self.assertEqual(r2['fast_flag'],0)
  progress=next(u for u in self.admin.call('/api/admin/overview')['users'] if u['id']==a.user['id']);self.assertEqual(progress['done'],1);self.assertEqual(progress['saves'],2)
  self.error(409,lambda:self.admin.call('/api/admin/audit',{'review_id':rid,'verdict':'needs_fix','note':'cũ'}))
  self.admin.call('/api/admin/users/toggle',{'user_id':a.user['id'],'active':False});self.error(401,lambda:a.call('/api/state'))
 def test_code_rotation_logout_and_rate_limit(self):
  member,created=self.member();new=self.admin.call('/api/admin/users/rotate',{'user_id':member.user['id']})
  self.error(401,lambda:member.call('/api/state'))
  self.error(401,lambda:Client(self.server.base,created['user']['username'],created['login_code']))
  fresh=Client(self.server.base,created['user']['username'],new['login_code']);fresh.call('/api/auth/logout',{});self.error(401,lambda:fresh.call('/api/state'))
  fake='missing'+uuid.uuid4().hex[:8]
  for _ in range(6):self.error(401,lambda:Client(self.server.base,fake,'wrong-code'))
  self.error(429,lambda:Client(self.server.base,fake,'wrong-code'))
 def test_preview_reclaim_and_immutable_old_reviews(self):
  member,_=self.member();plan=self.import_plan([member],2);self.admin.call('/api/admin/assign',{'plan':plan['plan']})
  held=member.call('/api/work/claim',{})['sample_id'];result=self.admin.call('/api/admin/users/reclaim',{'user_id':member.user['id']});self.assertEqual(result['reclaimed'],1)
  self.assertEqual([s['id'] for s in member.call('/api/state')['samples']],[held])

 def test_admin_crud_preserves_history_and_member_identity(self):
  member,created=self.member();text='CRUD '+uuid.uuid4().hex
  self.admin.call('/api/import',{'rows':[{'text':text,'source':'test','synthetic':True}]})
  sample=next(s for s in self.admin.call('/api/state')['samples'] if s['text']==text);sid=sample['id']
  self.error(403,lambda:member.call('/api/admin/samples/delete',{'sample_id':sid}))
  self.admin.call('/api/admin/samples/edit',{'sample_id':sid,'text':text+' sửa','context':'','source':'test','synthetic':True})
  self.admin.call('/api/admin/assign',{'plan':[{'user_id':member.user['id'],'sample_ids':[sid]}]})
  member.call('/api/work/claim',{'sample_id':sid})
  self.error(409,lambda:self.admin.call('/api/admin/samples/delete',{'sample_id':sid}))
  sample=next(s for s in member.call('/api/state')['samples'] if s['id']==sid)
  saved=member.call('/api/review',self.payload(member,sample))
  replacement=self.admin.call('/api/admin/samples/edit',{'sample_id':sid,'text':text+' nội dung thay thế','context':'ngữ cảnh mới','source':'test','synthetic':True})
  nid=replacement['replacement_sample_id'];self.assertNotEqual(nid,sid)
  self.assertEqual(self.admin.call('/api/admin/review?id='+str(saved['review_id']))['sample']['text'],text+' sửa')
  active=member.call('/api/state')['samples'];self.assertNotIn(sid,{s['id'] for s in active});self.assertIn(nid,{s['id'] for s in active})
  self.admin.call('/api/admin/samples/delete',{'sample_id':nid});self.assertNotIn(nid,{s['id'] for s in member.call('/api/state')['samples']})
  self.admin.call('/api/admin/samples/restore',{'sample_id':nid});self.assertIn(nid,{s['id'] for s in member.call('/api/state')['samples']})
  renamed=self.admin.call('/api/admin/users/edit',{'user_id':member.user['id'],'username':created['user']['username']+'x','display_name':'Tên đã sửa'})
  self.error(401,lambda:member.call('/api/state'));fresh=Client(self.server.base,renamed['user']['username'],renamed['login_code']);self.assertEqual(fresh.user['id'],member.user['id'])
  self.admin.call('/api/admin/users/delete',{'user_id':member.user['id']});self.error(401,lambda:fresh.call('/api/state'))
  restored=self.admin.call('/api/admin/users/restore',{'user_id':member.user['id']});self.assertEqual(Client(self.server.base,restored['user']['username'],restored['login_code']).user['id'],member.user['id'])

if __name__=='__main__':unittest.main(verbosity=2)
