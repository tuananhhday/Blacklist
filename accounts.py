"""Account codes, cookie sessions and server-side authorization."""
import hashlib,hmac,json,re,secrets,time
from pathlib import Path
from http.cookies import SimpleCookie

class Unauthorized(ValueError): pass
class Forbidden(ValueError): pass
class RateLimited(ValueError): pass

ITERATIONS=260000
SESSION_SECONDS=12*60*60

def hash_code(code):
 salt=secrets.token_hex(16)
 digest=hashlib.pbkdf2_hmac('sha256',code.encode(),bytes.fromhex(salt),ITERATIONS).hex()
 return f'{ITERATIONS}${salt}${digest}'

def verify(code,encoded):
 try:
  rounds,salt,expected=encoded.split('$')
  digest=hashlib.pbkdf2_hmac('sha256',code.encode(),bytes.fromhex(salt),int(rounds)).hex()
  return hmac.compare_digest(digest,expected)
 except (ValueError,TypeError):return False

DUMMY_HASH=hash_code('dummy-login-check')

def public(user):return {k:user[k] for k in ['id','username','display_name','role','active','deleted_at']}

def migrate(c,username,password,stamp):
 c.executescript((Path(__file__).parent/'sql/004_accounts.sql').read_text(encoding='utf8'))
 for table,columns in {
  'samples':{'archived_at':'TEXT','replacement_sample_id':'INTEGER REFERENCES samples(id)','needs_review':'INTEGER NOT NULL DEFAULT 0'},
  'auth_users':{'deleted_at':'TEXT'},
  'reviews':{'user_id':'INTEGER REFERENCES auth_users(id)','attempt_id':'INTEGER REFERENCES annotation_attempts(id)','elapsed_ms':'INTEGER','active_ms':'INTEGER','fast_flag':'INTEGER','threshold_ms':'INTEGER'},
  'rules':{'created_by_user_id':'INTEGER REFERENCES auth_users(id)'},
  'work_claims':{'user_id':'INTEGER REFERENCES auth_users(id)','attempt_id':'INTEGER REFERENCES annotation_attempts(id)'}
 }.items():
  existing={row[1] for row in c.execute('PRAGMA table_info('+table+')')}
  for column,kind in columns.items():
   if column not in existing:c.execute('ALTER TABLE '+table+' ADD COLUMN '+column+' '+kind)
 if password:
  found=c.execute('SELECT * FROM auth_users WHERE username=?',(username,)).fetchone()
  if not found:c.execute("INSERT INTO auth_users(username,display_name,code_hash,role,created_at) VALUES(?,?,?,'admin',?)",(username,'Quản trị viên',hash_code(password),stamp))
  elif found['role']!='admin':raise ValueError('Tên admin trùng tài khoản thành viên. Chọn STUDIO_USERNAME khác.')
  elif not verify(password,found['code_hash']):
   c.execute('UPDATE auth_users SET code_hash=?,active=1 WHERE id=?',(hash_code(password),found['id']))
   c.execute('DELETE FROM auth_sessions WHERE user_id=?',(found['id'],))
 if not c.execute("SELECT 1 FROM workspace_meta WHERE key='account_migration'").fetchone():
  c.execute('DELETE FROM work_claims')
  c.execute("INSERT INTO workspace_meta VALUES('account_migration','1')")

def login(c,o,peer):
 username=o.get('username','');code=o.get('code','')
 if not isinstance(username,str) or not isinstance(code,str) or len(username)>50 or len(code)>256:raise Unauthorized('Tài khoản hoặc mã đăng nhập không đúng.')
 username=username.strip().lower();key=hashlib.sha256((peer+'|'+username).encode()).hexdigest();now=time.time()
 limit=c.execute('SELECT * FROM login_limits WHERE key=?',(key,)).fetchone()
 if limit and now-limit['window_start']<600 and limit['attempts']>=6:raise RateLimited('Nhập sai nhiều lần. Chờ 10 phút hoặc nhờ admin đổi mã.')
 user=c.execute('SELECT * FROM auth_users WHERE username=?',(username,)).fetchone()
 correct=verify(code,user['code_hash'] if user else DUMMY_HASH)
 if not user or not correct or not user['active'] or user['deleted_at']:
  start=limit['window_start'] if limit and now-limit['window_start']<600 else now
  count=limit['attempts']+1 if limit and start==limit['window_start'] else 1
  c.execute('INSERT OR REPLACE INTO login_limits VALUES(?,?,?)',(key,count,start))
  return None
 c.execute('DELETE FROM login_limits WHERE key=?',(key,))
 c.execute('DELETE FROM auth_sessions WHERE expires_at<=?',(now,))
 raw=secrets.token_urlsafe(32);csrf=secrets.token_hex(24)
 c.execute('INSERT INTO auth_sessions VALUES(?,?,?,?)',(hashlib.sha256(raw.encode()).hexdigest(),user['id'],csrf,now+SESSION_SECONDS))
 return {'cookie':raw,'token':csrf,'user':public(user)}

def session(c,cookie):
 cookies=SimpleCookie()
 try:cookies.load(cookie or '')
 except Exception:return None
 value=cookies.get('studio_session')
 if not value:return None
 token_hash=hashlib.sha256(value.value.encode()).hexdigest()
 row=c.execute('''SELECT u.*,s.csrf,s.token_hash FROM auth_sessions s JOIN auth_users u ON u.id=s.user_id
   WHERE s.token_hash=? AND s.expires_at>? AND u.active=1 AND u.deleted_at IS NULL''',(token_hash,time.time())).fetchone()
 return dict(row) if row else None

def admin(user):
 if not user or user['role']!='admin':raise Forbidden('Chỉ admin được thực hiện thao tác này.')

def sample_access(c,user,sid,claim=False):
 sample=c.execute('SELECT archived_at FROM samples WHERE id=?',(sid,)).fetchone()
 if not sample or sample['archived_at']:raise Forbidden('Mẫu không còn trong hàng đợi hoạt động.')
 assignment=c.execute('SELECT * FROM task_assignments WHERE sample_id=?',(sid,)).fetchone()
 if user['role']=='admin':
  if claim and assignment and assignment['user_id']!=user['id']:raise Forbidden('Mẫu đã giao cho thành viên. Dùng màn giám sát để xem mà không lấy lượt của họ.')
 elif not assignment or assignment['user_id']!=user['id']:raise Forbidden('Bình luận này không nằm trong phần việc của bạn.')

def create_member(c,o,stamp):
 username=o.get('username','');name=o.get('display_name','')
 if not isinstance(username,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}',username):raise ValueError('Tài khoản dùng 3–40 chữ thường, số, dấu chấm, gạch ngang hoặc gạch dưới.')
 if not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('Nhập tên hiển thị, tối đa 100 ký tự.')
 if c.execute('SELECT 1 FROM auth_users WHERE username=?',(username,)).fetchone():raise ValueError('Tên tài khoản đã tồn tại.')
 code=secrets.token_urlsafe(12)
 uid=c.execute("INSERT INTO auth_users(username,display_name,code_hash,role,created_at) VALUES(?,?,?,'member',?)",(username,name.strip(),hash_code(code),stamp)).lastrowid
 return {'user':public(c.execute('SELECT * FROM auth_users WHERE id=?',(uid,)).fetchone()),'login_code':code}
