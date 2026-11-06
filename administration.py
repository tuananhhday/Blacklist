"""Admin allocation previews, account management and review quality monitoring."""
import json,secrets,statistics,time,hashlib,re,unicodedata
import accounts as auth
from collaboration import Conflict


def assignment_plan(c,o):
 ids=o.get('user_ids',[]);cap=o.get('per_user',0)
 if not isinstance(ids,list) or not ids or len(ids)>100 or any(type(x) is not int for x in ids) or len(ids)!=len(set(ids)):raise ValueError('Chọn các tài khoản thành viên nhận việc.')
 if type(cap) is not int or not 0<=cap<=5000:raise ValueError('Số câu/người cần từ 0 đến 5.000; 0 là chia hết.')
 people=[]
 for uid in ids:
  user=c.execute("SELECT * FROM auth_users WHERE id=? AND active=1 AND role='member' AND deleted_at IS NULL",(uid,)).fetchone()
  if not user:raise ValueError('Một tài khoản không còn hoạt động. Làm mới rồi chọn lại.')
  people.append(user)
 available=[r[0] for r in c.execute('''SELECT s.id FROM samples s WHERE s.archived_at IS NULL AND NOT EXISTS(SELECT 1 FROM task_assignments a WHERE a.sample_id=s.id)
   AND (s.needs_review=1 OR NOT EXISTS(SELECT 1 FROM reviews r WHERE r.sample_id=s.id))
   AND NOT EXISTS(SELECT 1 FROM work_claims w WHERE w.sample_id=s.id AND w.expires_at>?) ORDER BY s.id LIMIT 5000''',(time.time(),))]
 selected=available[:cap*len(ids)] if cap else available
 mapping=[{'user_id':u['id'],'display_name':u['display_name'],'sample_ids':selected[i::len(ids)]} for i,u in enumerate(people)]
 return {'plan':mapping,'total':len(selected),'available':len(available),'remaining':len(available)-len(selected)}

def apply_plan(c,o,actor,stamp):
 plan=o.get('plan')
 if not isinstance(plan,list) or not plan or len(plan)>100:raise ValueError('Xem trước phần chia việc trước.')
 seen=set();seen_users=set();pairs=[]
 for entry in plan:
  uid=entry.get('user_id');ids=entry.get('sample_ids')
  if type(uid) is not int or uid in seen_users or not isinstance(ids,list):raise ValueError('Kế hoạch chia không hợp lệ.')
  seen_users.add(uid)
  if not c.execute("SELECT 1 FROM auth_users WHERE id=? AND active=1 AND role='member' AND deleted_at IS NULL",(uid,)).fetchone():raise Conflict('Thành viên đã bị khóa. Xem trước lại.')
  for sid in ids:
   if type(sid) is not int or sid in seen:raise ValueError('Mỗi câu chỉ được giao cho một người.')
   seen.add(sid)
   if len(seen)>5000:raise ValueError('Tối đa 5.000 câu mỗi lần chia.')
   if not c.execute('SELECT 1 FROM samples WHERE id=?',(sid,)).fetchone():raise Conflict('Dữ liệu đã thay đổi. Xem trước lại.')
   if c.execute('SELECT 1 FROM task_assignments WHERE sample_id=?',(sid,)).fetchone() or c.execute('SELECT 1 FROM samples s WHERE s.id=? AND (s.archived_at IS NOT NULL OR (s.needs_review=0 AND EXISTS(SELECT 1 FROM reviews r WHERE r.sample_id=s.id)))',(sid,)).fetchone() or c.execute('SELECT 1 FROM work_claims WHERE sample_id=? AND expires_at>?',(sid,time.time())).fetchone():raise Conflict('Có câu vừa được nhận hoặc chia cho người khác. Xem trước lại; chưa chia một phần.')
   pairs.append((sid,uid,actor['id'],stamp))
 if not pairs:raise ValueError('Không có câu mới để chia.')
 c.executemany('INSERT INTO task_assignments(sample_id,user_id,assigned_by,assigned_at) VALUES(?,?,?,?)',pairs)
 return {'assigned':len(pairs),'users':len({pair[1] for pair in pairs})}

def manage_user(c,path,o,actor,stamp):
 uid=o.get('user_id');user=c.execute("SELECT * FROM auth_users WHERE id=? AND role='member'"+("" if path.endswith('/restore') else " AND deleted_at IS NULL"),(uid,)).fetchone()
 if not user:raise ValueError('Chỉ quản lý tài khoản thành viên ở đây.')
 if path.endswith('/restore'):
  code=secrets.token_urlsafe(12);c.execute('UPDATE auth_users SET active=1,deleted_at=NULL,code_hash=? WHERE id=?',(auth.hash_code(code),uid));result={'login_code':code,'user':auth.public(c.execute('SELECT * FROM auth_users WHERE id=?',(uid,)).fetchone())}
 elif path.endswith('/edit'):
  name=o.get('display_name','');username=o.get('username','')
  if not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('Tên hiển thị không hợp lệ.')
  if not isinstance(username,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}',username):raise ValueError('Tên tài khoản không hợp lệ.')
  if c.execute('SELECT 1 FROM auth_users WHERE username=? AND id<>?',(username,uid)).fetchone():raise ValueError('Tài khoản đã tồn tại.')
  c.execute('UPDATE auth_users SET display_name=?,username=? WHERE id=?',(name.strip(),username,uid))
  result={'updated':True}
  if username!=user['username']:
   code=secrets.token_urlsafe(12);c.execute('UPDATE auth_users SET code_hash=? WHERE id=?',(auth.hash_code(code),uid));result['login_code']=code
  result['user']=auth.public(c.execute('SELECT * FROM auth_users WHERE id=?',(uid,)).fetchone())
 elif path.endswith('/delete'):
  c.execute('UPDATE auth_users SET active=0,deleted_at=? WHERE id=?',(stamp,uid));result={'deleted':True}
  c.execute("DELETE FROM task_assignments WHERE user_id=? AND state='pending'",(uid,))
 elif path.endswith('/rotate'):
  code=secrets.token_urlsafe(12);c.execute('UPDATE auth_users SET code_hash=? WHERE id=?',(auth.hash_code(code),uid));result={'login_code':code,'user':auth.public(user)}
 elif path.endswith('/toggle'):
  active=o.get('active')
  if type(active) is not bool:raise ValueError('Trạng thái tài khoản không hợp lệ.')
  c.execute('UPDATE auth_users SET active=? WHERE id=?',(int(active),uid));result={'active':active}
 elif path.endswith('/reclaim'):
  pending=[r[0] for r in c.execute("SELECT sample_id FROM task_assignments WHERE user_id=? AND state='pending' AND NOT EXISTS(SELECT 1 FROM work_claims w WHERE w.sample_id=task_assignments.sample_id AND w.expires_at>?)",(uid,time.time()))]
  for sid in pending:c.execute('DELETE FROM task_assignments WHERE sample_id=?',(sid,))
  return {'reclaimed':len(pending)}
 else:raise ValueError('Thao tác tài khoản không hợp lệ.')
 c.execute('DELETE FROM auth_sessions WHERE user_id=?',(uid,))
 c.execute('DELETE FROM work_claims WHERE user_id=?',(uid,))
 c.execute('UPDATE annotation_attempts SET closed_at=? WHERE user_id=? AND closed_at IS NULL',(time.time(),uid))
 return result

def overview(c):
 people=[]
 for user in c.execute("SELECT * FROM auth_users ORDER BY role,username"):
  uid=user['id'];row=auth.public(user)
  counts=c.execute("SELECT COUNT(*),SUM(a.state='done') FROM task_assignments a JOIN samples s ON s.id=a.sample_id WHERE a.user_id=? AND s.archived_at IS NULL",(uid,)).fetchone()
  row.update(assigned=counts[0],done=counts[1] or 0,pending=counts[0]-(counts[1] or 0))
  timings=[r[0]/1000 for r in c.execute('SELECT elapsed_ms FROM reviews WHERE user_id=? AND elapsed_ms IS NOT NULL ORDER BY id DESC LIMIT 200',(uid,))]
  stats=c.execute('SELECT COUNT(*),SUM(fast_flag=1),MAX(created_at) FROM reviews WHERE user_id=?',(uid,)).fetchone()
  row.update(saves=stats[0],fast=stats[1] or 0,last_save=stats[2],median_seconds=round(statistics.median(timings),1) if timings else None)
  row['draft_rules']=c.execute("SELECT COUNT(*) FROM rules WHERE created_by_user_id=? AND status='draft'",(uid,)).fetchone()[0]
  row['held']=[r[0] for r in c.execute('SELECT sample_id FROM work_claims WHERE user_id=? AND expires_at>?',(uid,time.time()))]
  people.append(row)
 return {'users':people,'total_samples':c.execute('SELECT COUNT(*) FROM samples WHERE archived_at IS NULL').fetchone()[0],
  'unassigned':c.execute('SELECT COUNT(*) FROM samples s WHERE s.archived_at IS NULL AND NOT EXISTS(SELECT 1 FROM task_assignments a WHERE a.sample_id=s.id) AND (s.needs_review=1 OR NOT EXISTS(SELECT 1 FROM reviews r WHERE r.sample_id=s.id))').fetchone()[0],
  'fast_seconds':float(c.execute("SELECT value FROM workspace_meta WHERE key='fast_seconds'").fetchone()[0]),
  'draft_rules':c.execute("SELECT COUNT(*) FROM rules WHERE status='draft'").fetchone()[0]}

def review_list(c,query):
 where=[];args=[]
 uid=query.get('user_id',[''])[0];fast=query.get('fast',['0'])[0]
 if uid:
  where.append('r.user_id=?');args.append(int(uid))
 if fast=='1':where.append('r.fast_flag=1')
 condition=' WHERE '+' AND '.join(where) if where else ''
 page=max(0,int(query.get('page',['0'])[0]));limit=40
 total=c.execute('SELECT COUNT(*) FROM reviews r'+condition,args).fetchone()[0]
 rows=[dict(r) for r in c.execute('''SELECT r.id,r.sample_id,r.revision,r.reviewer,r.decision,r.created_at,r.elapsed_ms,r.active_ms,r.fast_flag,r.threshold_ms,
  substr(s.text,1,180) AS text,u.username,a.verdict AS audit_verdict
  FROM reviews r JOIN samples s ON s.id=r.sample_id LEFT JOIN auth_users u ON u.id=r.user_id
  LEFT JOIN review_audits a ON a.review_id=r.id'''+condition+' ORDER BY r.id DESC LIMIT ? OFFSET ?',args+[limit,page*limit])]
 return {'reviews':rows,'total':total,'page':page,'page_size':limit}

def review_detail(c,rid):
 row=c.execute('SELECT * FROM reviews WHERE id=?',(rid,)).fetchone()
 if not row:raise ValueError('Không có lần duyệt này.')
 review=dict(row);review['labels']=json.loads(review['labels_json'])
 sample=dict(c.execute('SELECT * FROM samples WHERE id=?',(row['sample_id'],)).fetchone())
 audit=c.execute('SELECT * FROM review_audits WHERE review_id=?',(rid,)).fetchone()
 return {'review':review,'sample':sample,'audit':dict(audit) if audit else None}

def audit_review(c,o,actor,stamp):
 rid=o.get('review_id');verdict=o.get('verdict');note=o.get('note','')
 if verdict not in ['approved','needs_fix'] or not isinstance(note,str) or len(note)>2000:raise ValueError('Kết quả kiểm tra không hợp lệ.')
 if verdict=='needs_fix' and not note.strip():raise ValueError('Ghi lý do để thành viên biết cần sửa gì.')
 review=c.execute('SELECT * FROM reviews WHERE id=?',(rid,)).fetchone()
 if not review:raise ValueError('Không có lần duyệt này.')
 if verdict=='needs_fix':
  if c.execute('SELECT archived_at FROM samples WHERE id=?',(review['sample_id'],)).fetchone()[0]:raise ValueError('Bình luận đang được lưu trữ hoặc thay thế. Khôi phục trước khi trả lại để sửa.')
  latest=c.execute('SELECT MAX(revision) FROM reviews WHERE sample_id=?',(review['sample_id'],)).fetchone()[0]
  if latest!=review['revision']:raise Conflict('Đã có phiên bản nhãn mới. Kiểm tra phiên bản mới nhất trước khi yêu cầu sửa.')
  if not review['user_id']:raise ValueError('Nhãn cũ chưa gắn tài khoản; admin cần xem và sửa trực tiếp.')
  if c.execute('SELECT 1 FROM work_claims WHERE sample_id=? AND expires_at>?',(review['sample_id'],time.time())).fetchone():raise Conflict('Mẫu đang có người xử lý. Chờ họ lưu hoặc hết lượt trước khi trả lại.')
  c.execute('UPDATE samples SET needs_review=1 WHERE id=?',(review['sample_id'],))
  c.execute("INSERT INTO task_assignments VALUES(?,?,?,?,'pending') ON CONFLICT(sample_id) DO UPDATE SET state='pending'",(review['sample_id'],review['user_id'],actor['id'],stamp))
 if verdict=='approved':
  latest=c.execute('SELECT MAX(revision) FROM reviews WHERE sample_id=?',(review['sample_id'],)).fetchone()[0]
  if latest==review['revision']:
   c.execute('UPDATE samples SET needs_review=0 WHERE id=?',(review['sample_id'],))
   c.execute("UPDATE task_assignments SET state='done' WHERE sample_id=?",(review['sample_id'],))
 c.execute('INSERT OR REPLACE INTO review_audits VALUES(?,?,?,?,?)',(rid,actor['id'],verdict,note.strip(),stamp))
 return {'audited':True,'verdict':verdict}


def sample_list(c,query):
 archived=query.get('archived',['0'])[0]=='1';q=query.get('q',[''])[0][:200];page=max(0,int(query.get('page',['0'])[0]));args=['%'+q+'%']
 where='s.archived_at IS '+('NOT NULL' if archived else 'NULL')+' AND s.text LIKE ?'
 total=c.execute('SELECT COUNT(*) FROM samples s WHERE '+where,args).fetchone()[0]
 rows=[dict(r) for r in c.execute("SELECT s.*,u.display_name AS assigned_name,(SELECT COUNT(*) FROM reviews r WHERE r.sample_id=s.id) AS review_count FROM samples s LEFT JOIN task_assignments a ON a.sample_id=s.id LEFT JOIN auth_users u ON u.id=a.user_id WHERE "+where+' ORDER BY s.id DESC LIMIT 40 OFFSET ?',args+[page*40])]
 return {'samples':rows,'total':total,'page':page,'page_size':40}

def edit_sample(c,path,o,actor,stamp):
 sid=o.get('sample_id');sample=c.execute('SELECT * FROM samples WHERE id=?',(sid,)).fetchone()
 if not sample:raise ValueError('Không có bình luận này.')
 if c.execute('SELECT 1 FROM work_claims WHERE sample_id=? AND expires_at>?',(sid,time.time())).fetchone():raise Conflict('Bình luận đang có người xử lý. Chờ lưu xong hoặc hết lượt rồi sửa/xóa.')
 if path.endswith('/restore'):
  c.execute('UPDATE samples SET archived_at=NULL WHERE id=?',(sid,));return {'restored':True}
 if path.endswith('/delete'):
  c.execute('UPDATE samples SET archived_at=? WHERE id=?',(stamp,sid));return {'deleted':True}
 if sample['archived_at']:raise ValueError('Khôi phục bình luận trước khi sửa.')
 text=o.get('text','');context=o.get('context','');source=o.get('source','');synthetic=o.get('synthetic')
 if not isinstance(text,str) or not text.strip() or len(text)>20000 or not isinstance(context,str) or len(context)>20000 or not isinstance(source,str) or not source.strip() or len(source)>500 or type(synthetic) is not bool:raise ValueError('Nội dung, nguồn hoặc loại dữ liệu không hợp lệ.')
 normalize=lambda value:re.sub(r'\s+',' ',unicodedata.normalize('NFC',value)).strip().casefold()
 fp=hashlib.sha256((normalize(text)+'\x00'+normalize(context)).encode()).hexdigest()
 duplicate=c.execute('SELECT id FROM samples WHERE fingerprint=? AND id<>?',(fp,sid)).fetchone()
 if duplicate:raise ValueError('Nội dung trùng bình luận #'+str(duplicate[0])+'. Không tạo bản trùng.')
 changed_text=text.strip()!=sample['text'] or context.strip()!=sample['context']
 reviewed=c.execute('SELECT 1 FROM reviews WHERE sample_id=?',(sid,)).fetchone()
 if changed_text and reviewed and fp==sample['fingerprint']:raise ValueError('Nội dung chỉ khác chữ hoa hoặc khoảng trắng. Giữ bản gốc để bảo toàn nhãn và bằng chứng đã lưu.')
 if changed_text and reviewed:
  new_id=c.execute('INSERT INTO samples(text,context,source,synthetic,fingerprint,created_at) VALUES(?,?,?,?,?,?)',(text.strip(),context.strip(),source.strip(),int(synthetic),fp,stamp)).lastrowid
  c.execute('UPDATE samples SET archived_at=?,replacement_sample_id=? WHERE id=?',(stamp,new_id,sid))
  assigned=c.execute('SELECT a.* FROM task_assignments a JOIN auth_users u ON u.id=a.user_id WHERE a.sample_id=? AND u.active=1 AND u.deleted_at IS NULL',(sid,)).fetchone()
  if assigned:c.execute("INSERT INTO task_assignments VALUES(?,?,?,?,'pending')",(new_id,assigned['user_id'],actor['id'],stamp))
  return {'updated':True,'replacement_sample_id':new_id,'message':'Đã tạo mẫu thay thế; giữ nguyên nhãn và lịch sử bản cũ.'}
 if changed_text:c.execute('DELETE FROM work_drafts WHERE sample_id=?',(sid,))
 c.execute('UPDATE samples SET text=?,context=?,source=?,synthetic=?,fingerprint=? WHERE id=?',(text.strip(),context.strip(),source.strip(),int(synthetic),fp,sid))
 return {'updated':True,'sample_id':sid}
