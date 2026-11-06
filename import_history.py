"""Reversible import batches: link only newly inserted samples, never duplicates."""
import json,re,time,uuid,hashlib,unicodedata
from pathlib import Path
from collaboration import Conflict

SCHEMA=(Path(__file__).parent/'sql/005_import_history.sql').read_text(encoding='utf8')

def begin(c,o,user,stamp):
 key=o.get('import_batch_id') or uuid.uuid4().hex
 if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{32}',key):raise ValueError('Mã đợt nhập không hợp lệ.')
 name=o.get('import_name') or 'Thêm bình luận'
 if not isinstance(name,str) or not name.strip() or len(name)>500:raise ValueError('Tên đợt nhập cần từ 1–500 ký tự.')
 current=c.execute('SELECT * FROM import_batches WHERE id=?',(key,)).fetchone()
 if current:
  if current['user_id']!=user['id']:raise ValueError('Đợt nhập không thuộc tài khoản này.')
  if current['status']!='active':raise Conflict('Đợt nhập đã hoàn tác. Khôi phục đợt hoặc xem trước để tạo đợt mới.')
 else:c.execute('INSERT INTO import_batches(id,name,user_id,created_at,updated_at) VALUES(?,?,?,?,?)',(key,name.strip(),user['id'],stamp,stamp))
 return key

def finish(c,key,inserted,requested,stamp):
 c.executemany('INSERT OR IGNORE INTO import_batch_samples(batch_id,sample_id) VALUES(?,?)',[(key,sid) for sid in inserted])
 c.execute('UPDATE import_batches SET requested=requested+?,added=added+?,duplicates=duplicates+?,updated_at=? WHERE id=?',(requested,len(inserted),requested-len(inserted),stamp,key))

def list_batches(c,page=0):
 page=max(0,int(page));total=c.execute('SELECT COUNT(*) FROM import_batches').fetchone()[0]
 rows=[dict(r) for r in c.execute('''SELECT b.*,u.display_name AS created_by,
 (SELECT COUNT(*) FROM import_batch_samples l JOIN samples s ON s.id=l.sample_id WHERE l.batch_id=b.id AND s.archived_at IS NULL) AS visible
 FROM import_batches b JOIN auth_users u ON u.id=b.user_id ORDER BY b.created_at DESC LIMIT 20 OFFSET ?''',(page*20,))]
 return {'batches':rows,'total':total,'page':page,'page_size':20}

def change(c,action,o,stamp):
 key=o.get('batch_id');batch=c.execute('SELECT * FROM import_batches WHERE id=?',(key,)).fetchone()
 if not batch:raise ValueError('Không có đợt nhập này.')
 if action=='undo':
  if c.execute("SELECT 1 FROM parquet_import_runs WHERE batch_id=? AND state='running'",(key,)).fetchone():raise Conflict('File vẫn đang nhập. Bấm Tạm dừng, chờ dừng xong rồi hoàn tác đợt.')
  if batch['status']=='undone':return {'status':'undone','changed':0}
  live=c.execute('''SELECT COUNT(*) FROM import_batch_samples l JOIN work_claims w ON w.sample_id=l.sample_id
    WHERE l.batch_id=? AND w.expires_at>?''',(key,time.time())).fetchone()[0]
  if live:raise Conflict(f'Có {live} bình luận đang được xử lý. Chờ lưu hoặc hết lượt trước khi hoàn tác; chưa thay đổi dữ liệu.')
  active_rules=c.execute("SELECT COUNT(*) FROM import_batch_samples l JOIN rules r ON r.source_sample_id=l.sample_id WHERE l.batch_id=? AND r.status='active'",(key,)).fetchone()[0]
  if active_rules:raise Conflict('Có blacklist đang bật từ đợt này. Kiểm tra/tắt các luật đó trước khi hoàn tác dữ liệu.')
  ids=[r[0] for r in c.execute('''SELECT l.sample_id FROM import_batch_samples l JOIN samples s ON s.id=l.sample_id
    WHERE l.batch_id=? AND s.archived_at IS NULL''',(key,))]
  c.execute('UPDATE import_batch_samples SET undo_archived_at=NULL WHERE batch_id=?',(key,))
  for sid in ids:
   c.execute('UPDATE samples SET archived_at=? WHERE id=?',(stamp,sid))
   c.execute('UPDATE import_batch_samples SET undo_archived_at=? WHERE batch_id=? AND sample_id=?',(stamp,key,sid))
  c.execute("UPDATE import_batches SET status='undone',updated_at=? WHERE id=?",(stamp,key))
  return {'status':'undone','changed':len(ids),'message':'Đã ẩn các bình luận mới của đợt này; giữ nguyên dữ liệu trùng có sẵn và lịch sử nhãn.'}
 if action=='restore':
  if batch['status']=='active':return {'status':'active','changed':0}
  ids=[r[0] for r in c.execute('''SELECT l.sample_id FROM import_batch_samples l JOIN samples s ON s.id=l.sample_id
    WHERE l.batch_id=? AND l.undo_archived_at IS NOT NULL AND s.archived_at=l.undo_archived_at''',(key,))]
  for sid in ids:c.execute('UPDATE samples SET archived_at=NULL WHERE id=?',(sid,))
  c.execute('UPDATE import_batch_samples SET undo_archived_at=NULL WHERE batch_id=?',(key,))
  c.execute("UPDATE import_batches SET status='active',updated_at=? WHERE id=?",(stamp,key))
  return {'status':'active','changed':len(ids),'message':'Đã khôi phục các bình luận do lần hoàn tác này ẩn. Các lần xóa riêng được giữ nguyên.'}
 raise ValueError('Thao tác đợt nhập không hợp lệ.')


def store_rows(c,rows,key,stamp):
 inserted=[]
 normalize=lambda value:re.sub(r'\s+',' ',unicodedata.normalize('NFC',value)).strip().casefold()
 for row in rows:
  if not isinstance(row,dict):raise ValueError('Mỗi bình luận cần là object.')
  text=row.get('text','');context=row.get('context','');source=row.get('source','');synthetic=row.get('synthetic',True)
  if not isinstance(text,str) or not text.strip() or len(text)>20000:raise ValueError('Nội dung cần từ 1–20.000 ký tự.')
  if not isinstance(context,str) or len(context)>20000:raise ValueError('Ngữ cảnh tối đa 20.000 ký tự.')
  if not isinstance(source,str) or not source.strip() or len(source)>500:raise ValueError('Nguồn cần từ 1–500 ký tự.')
  if type(synthetic) is not bool:raise ValueError('synthetic cần true/false.')
  fingerprint=hashlib.sha256((normalize(text)+'\x00'+normalize(context)).encode()).hexdigest()
  cursor=c.execute('INSERT OR IGNORE INTO samples(text,context,source,synthetic,fingerprint,created_at) VALUES(?,?,?,?,?,?)',(text.strip(),context.strip(),source.strip(),int(synthetic),fingerprint,stamp))
  if cursor.rowcount:inserted.append(cursor.lastrowid)
 finish(c,key,inserted,len(rows),stamp)
 return {'added':len(inserted),'duplicates':len(rows)-len(inserted),'import_batch_id':key}
