"""Transactional work leases and recoverable drafts for one SQLite instance."""
import hashlib, json, re, time
import accounts as auth

LEASE_SECONDS = 180
from pathlib import Path
SCHEMA = (Path(__file__).parent/'sql/003_collaboration.sql').read_text(encoding='utf8')

class Conflict(ValueError): pass

def scope_sql(user):
 if user and user['role']=='member':return "s.archived_at IS NULL AND a.user_id=? AND a.state='pending'",[user['id']]
 if user:return "((a.sample_id IS NULL AND NOT EXISTS(SELECT 1 FROM reviews r WHERE r.sample_id=s.id)) OR (s.archived_at IS NULL AND a.user_id=? AND a.state='pending'))",[user['id']]
 return 's.archived_at IS NULL AND NOT EXISTS(SELECT 1 FROM reviews r WHERE r.sample_id=s.id)',[]

def eligible(c,user,sid):
 scope,args=scope_sql(user)
 return bool(c.execute('SELECT 1 FROM samples s LEFT JOIN task_assignments a ON a.sample_id=s.id WHERE s.id=? AND '+scope,[sid]+args).fetchone())

def heartbeat(c,o):
 sid=o.get('sample_id');check_claim(c,sid,o)
 claim=c.execute('SELECT * FROM work_claims WHERE sample_id=?',(sid,)).fetchone()
 if not claim['attempt_id']:return
 attempt=c.execute('SELECT * FROM annotation_attempts WHERE id=?',(claim['attempt_id'],)).fetchone()
 stamp=time.time();gap=max(0,stamp-attempt['last_seen_at']);active=o.get('active') is True
 extra=gap if gap<=45 and active and attempt['was_active'] else 0
 c.execute('UPDATE annotation_attempts SET last_seen_at=?,active_seconds=active_seconds+?,was_active=? WHERE id=?',(stamp,extra,int(active),attempt['id']))

def finish_timing(c,o):
 heartbeat(c,o)
 claim=c.execute('SELECT * FROM work_claims WHERE sample_id=?',(o.get('sample_id'),)).fetchone()
 attempt=c.execute('SELECT * FROM annotation_attempts WHERE id=?',(claim['attempt_id'],)).fetchone()
 if not attempt:raise Conflict('Không tìm thấy lượt làm việc. Nhận lại câu trước khi lưu.')
 stamp=o.get('_received_at',time.time());elapsed=max(0,round((stamp-attempt['started_at'])*1000));active=min(elapsed,round(attempt['active_seconds']*1000))
 threshold=round(float(c.execute("SELECT value FROM workspace_meta WHERE key='fast_seconds'").fetchone()[0])*1000)
 c.execute('UPDATE annotation_attempts SET closed_at=? WHERE id=?',(stamp,attempt['id']))
 return {'attempt_id':attempt['id'],'elapsed_ms':elapsed,'active_ms':active,'threshold_ms':threshold,'fast_flag':int(elapsed<threshold)}


def owner(o):
 value=o.get('client_id','')
 if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{32,64}',value):
  raise ValueError('Thiếu mã phiên làm việc. Tải lại trang để kết nối lại.')
 return hashlib.sha256(value.encode()).hexdigest()

def check_claim(c,sample_id,o):
 current=c.execute('SELECT * FROM work_claims WHERE sample_id=?',(sample_id,)).fetchone()
 if not current or current['owner']!=owner(o) or current['expires_at']<=time.time():
  raise Conflict('Lượt giữ mẫu đã hết hoặc thuộc người khác. Nháp của bạn vẫn được giữ; hãy nhận lại mẫu trước khi lưu.')
 if o.get('_user'):auth.sample_access(c,o['_user'],sample_id,claim=True)
 c.execute('UPDATE work_claims SET expires_at=? WHERE sample_id=?',(time.time()+LEASE_SECONDS,sample_id))

def claim(c,o):
 ident=owner(o);reviewer=o.get('reviewer','').strip()
 if not reviewer or len(reviewer)>100:raise ValueError('Nhập tên người gán nhãn trước khi nhận mẫu.')
 c.execute('DELETE FROM work_claims WHERE expires_at<=?',(time.time(),))
 sid=o.get('sample_id');exclude=o.get('exclude_id');user=o.get('_user')
 if sid is None:
  existing=c.execute('SELECT sample_id FROM work_claims WHERE owner=?',(ident,)).fetchone()
  if existing and existing[0]!=exclude and eligible(c,user,existing[0]):sid=existing[0]
  else:
   scope,args=scope_sql(user)
   row=c.execute("SELECT s.id FROM samples s LEFT JOIN task_assignments a ON a.sample_id=s.id WHERE "+scope+" AND NOT EXISTS(SELECT 1 FROM work_claims w WHERE w.sample_id=s.id AND w.owner<>? AND w.expires_at>?) AND s.id<>? ORDER BY s.id LIMIT 1",args+[ident,time.time(),exclude or -1]).fetchone()
   if row:sid=row[0]
 if sid is None:
  if not exclude:
   c.execute('DELETE FROM work_claims WHERE owner=?',(ident,))
   c.execute('UPDATE annotation_attempts SET closed_at=? WHERE owner=? AND closed_at IS NULL',(time.time(),ident))
  return {'sample_id':None,'message':'Không còn mẫu đang chờ hoặc các mẫu đã được người khác nhận.'}
 if user:auth.sample_access(c,user,sid,claim=True)
 if not c.execute('SELECT 1 FROM samples WHERE id=?',(sid,)).fetchone():raise ValueError('Không có mẫu này.')
 current=c.execute('SELECT * FROM work_claims WHERE sample_id=?',(sid,)).fetchone()
 if current and current['owner']!=ident:raise Conflict('Mẫu này đang được người khác gán nhãn. Chọn câu khác hoặc nhận mẫu tiếp theo.')
 c.execute('DELETE FROM work_claims WHERE owner=?',(ident,))
 uid=user['id'] if user else None
 attempt=None
 if current and current['owner']==ident and current['expires_at']>time.time():attempt=current['attempt_id']
 if uid and not attempt:
  c.execute('UPDATE annotation_attempts SET closed_at=? WHERE owner=? AND closed_at IS NULL',(time.time(),ident))
  attempt=c.execute('INSERT INTO annotation_attempts(sample_id,user_id,owner,started_at,last_seen_at) VALUES(?,?,?,?,?)',(sid,uid,ident,time.time(),time.time())).lastrowid
 c.execute('INSERT OR REPLACE INTO work_claims(sample_id,owner,reviewer,expires_at,user_id,attempt_id) VALUES(?,?,?,?,?,?)',(sid,ident,reviewer,time.time()+LEASE_SECONDS,uid,attempt))
 draft=c.execute('SELECT payload_json FROM work_drafts WHERE owner=? AND sample_id=?',(ident,sid)).fetchone()
 started=c.execute('SELECT started_at FROM annotation_attempts WHERE id=?',(attempt,)).fetchone() if attempt else None
 return {'sample_id':sid,'attempt_started_at':started[0] if started else None,'lease_seconds':LEASE_SECONDS,'draft':json.loads(draft[0]) if draft else None}

def save_draft(c,o,stamp):
 sid=o.get('sample_id');check_claim(c,sid,o)
 draft=o.get('draft')
 if not isinstance(draft,dict):raise ValueError('Bản nháp không hợp lệ.')
 payload=json.dumps(draft,ensure_ascii=False,allow_nan=False)
 if len(payload.encode())>100000:raise ValueError('Bản nháp quá lớn.')
 previous=c.execute('SELECT payload_json FROM work_drafts WHERE owner=? AND sample_id=?',(owner(o),sid)).fetchone()
 if previous and previous[0]==payload:return False
 c.execute('INSERT OR REPLACE INTO work_drafts VALUES(?,?,?,?)',(owner(o),sid,payload,stamp));return True
