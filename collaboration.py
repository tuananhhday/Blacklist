"""Transactional work leases and recoverable drafts for one SQLite instance."""
import hashlib, json, re, time

LEASE_SECONDS = 180
from pathlib import Path
SCHEMA = (Path(__file__).parent/'sql/003_collaboration.sql').read_text(encoding='utf8')

class Conflict(ValueError): pass

def owner(o):
 value=o.get('client_id','')
 if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{32,64}',value):
  raise ValueError('Thiếu mã phiên làm việc. Tải lại trang để kết nối lại.')
 return hashlib.sha256(value.encode()).hexdigest()

def check_claim(c,sample_id,o):
 current=c.execute('SELECT * FROM work_claims WHERE sample_id=?',(sample_id,)).fetchone()
 if not current or current['owner']!=owner(o) or current['expires_at']<=time.time():
  raise Conflict('Lượt giữ mẫu đã hết hoặc thuộc người khác. Nháp của bạn vẫn được giữ; hãy nhận lại mẫu trước khi lưu.')
 c.execute('UPDATE work_claims SET expires_at=? WHERE sample_id=?',(time.time()+LEASE_SECONDS,sample_id))

def claim(c,o):
 ident=owner(o);reviewer=o.get('reviewer','').strip()
 if not reviewer or len(reviewer)>100:raise ValueError('Nhập tên người gán nhãn trước khi nhận mẫu.')
 c.execute('DELETE FROM work_claims WHERE expires_at<=?',(time.time(),))
 sid=o.get('sample_id');exclude=o.get('exclude_id')
 if sid is None:
  existing=c.execute('SELECT sample_id FROM work_claims WHERE owner=?',(ident,)).fetchone()
  if existing and existing[0]!=exclude:sid=existing[0]
  else:
   row=c.execute('''SELECT s.id FROM samples s WHERE NOT EXISTS(SELECT 1 FROM reviews r WHERE r.sample_id=s.id)
     AND NOT EXISTS(SELECT 1 FROM work_claims w WHERE w.sample_id=s.id AND w.owner<>?)
     AND s.id<>? ORDER BY s.id LIMIT 1''',(ident,exclude or -1)).fetchone()
   if row:sid=row[0]
 if sid is None:return {'sample_id':None,'message':'Không còn mẫu đang chờ hoặc các mẫu đã được người khác nhận.'}
 if not c.execute('SELECT 1 FROM samples WHERE id=?',(sid,)).fetchone():raise ValueError('Không có mẫu này.')
 current=c.execute('SELECT * FROM work_claims WHERE sample_id=?',(sid,)).fetchone()
 if current and current['owner']!=ident:raise Conflict('Mẫu này đang được người khác gán nhãn. Chọn câu khác hoặc nhận mẫu tiếp theo.')
 c.execute('DELETE FROM work_claims WHERE owner=?',(ident,))
 c.execute('INSERT OR REPLACE INTO work_claims VALUES(?,?,?,?)',(sid,ident,reviewer,time.time()+LEASE_SECONDS))
 draft=c.execute('SELECT payload_json FROM work_drafts WHERE owner=? AND sample_id=?',(ident,sid)).fetchone()
 return {'sample_id':sid,'lease_seconds':LEASE_SECONDS,'draft':json.loads(draft[0]) if draft else None}

def save_draft(c,o,stamp):
 sid=o.get('sample_id');check_claim(c,sid,o)
 draft=o.get('draft')
 if not isinstance(draft,dict):raise ValueError('Bản nháp không hợp lệ.')
 payload=json.dumps(draft,ensure_ascii=False,allow_nan=False)
 if len(payload.encode())>100000:raise ValueError('Bản nháp quá lớn.')
 previous=c.execute('SELECT payload_json FROM work_drafts WHERE owner=? AND sample_id=?',(owner(o),sid)).fetchone()
 if previous and previous[0]==payload:return False
 c.execute('INSERT OR REPLACE INTO work_drafts VALUES(?,?,?,?)',(owner(o),sid,payload,stamp));return True
