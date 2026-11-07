"""Structured blacklist proposals from saved labels, with immutable source evidence."""
import hashlib,json,re,unicodedata
import accounts as auth
from collaboration import Conflict

def normalize(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFC',value)).strip().casefold()

def source(c,user,sid,review_id=None):
 auth.sample_access(c,user,sid)
 sample=c.execute('SELECT * FROM samples WHERE id=?',(sid,)).fetchone()
 latest=c.execute('SELECT * FROM reviews WHERE sample_id=? ORDER BY revision DESC LIMIT 1',(sid,)).fetchone()
 if not latest or latest['decision']!='VIOLATION' or sample['needs_review']:raise ValueError('Lưu nhãn Vi phạm đã xác minh trước khi gửi Blacklist nháp.')
 if review_id is not None and review_id!=latest['id']:raise Conflict('Nhãn nguồn đã đổi. Tải lại kết quả trước khi tạo nháp.')
 if user['role']=='member' and latest['user_id']!=user['id']:raise auth.Forbidden('Chỉ đề xuất từ kết quả gán nhãn của bạn trong phần việc được giao.')
 return sample,latest

def propose(c,user,o,stamp):
 sample,review=source(c,user,o.get('sample_id'),o.get('review_id'))
 evidence=o.get('candidate_evidence','')
 if not isinstance(evidence,str) or len(evidence)>20000:raise ValueError('Đoạn đặc trưng cần là văn bản, tối đa 20.000 ký tự.')
 evidence=evidence.strip() or review['evidence'] or sample['text']
 if evidence not in sample['text']:raise ValueError('Đoạn đặc trưng phải nằm nguyên văn trong bình luận nguồn.')
 labels=json.loads(review['labels_json']);results=[]
 for category,value in labels.items():
  if value!=1:continue
  key=hashlib.sha256((str(user['id'])+'|'+str(review['id'])+'|'+category+'|'+normalize(evidence)).encode()).hexdigest()
  existing=c.execute('SELECT id,name,status FROM rules WHERE proposal_key=?',(key,)).fetchone()
  if existing:results.append({'id':existing['id'],'name':existing['name'],'category':category,'created':False});continue
  name=c.execute('SELECT name FROM categories WHERE code=?',(category,)).fetchone()[0]+' · câu #'+str(sample['id'])
  config=json.dumps({'pattern':sample['text']},ensure_ascii=False);tests=json.dumps([{'text':sample['text'],'expected':'MATCH'}],ensure_ascii=False)
  cursor=c.execute("""INSERT INTO rules(name,category,kind,config_json,tests_json,status,version,source_sample_id,reviewer,reason,updated_at,created_by_user_id,
   intent,evidence,source_review_id,source_text,source_context,source_labels_json,proposal_key)
   VALUES(?,?,'exact',?,?,'draft',1,?,?,?,?,?,'',?,?,?,?,?,?)""",
   (name,category,config,tests,sample['id'],user['display_name'],review['reason'] or 'Đề xuất từ nhãn Vi phạm đã lưu.',stamp,user['id'],evidence,review['id'],sample['text'],sample['context'],review['labels_json'],key))
  if review['intent']:c.execute('UPDATE rules SET intent=? WHERE id=?',(review['intent'],cursor.lastrowid))
  rule=dict(c.execute('SELECT * FROM rules WHERE id=?',(cursor.lastrowid,)).fetchone())
  c.execute('INSERT INTO rule_history(rule_id,version,snapshot_json,created_at) VALUES(?,1,?,?)',(cursor.lastrowid,json.dumps(rule,ensure_ascii=False),stamp))
  results.append({'id':cursor.lastrowid,'name':name,'category':category,'created':True})
 if not results:raise ValueError('Cần ít nhất một nhóm vi phạm để tạo nháp.')
 return {'proposals':results,'sample_id':sample['id'],'review_id':review['id']}

def details(c,rule):
 # API output explicitly separates source labels from editable rule configuration.
 rule['source_labels']=json.loads(rule.pop('source_labels_json','{}') or '{}')
 sid=rule.get('source_sample_id');rid=rule.get('source_review_id')
 rule['source_stale']=False
 if sid and rid:
  current=c.execute('SELECT id FROM reviews WHERE sample_id=? ORDER BY revision DESC LIMIT 1',(sid,)).fetchone()
  sample=c.execute('SELECT archived_at,needs_review FROM samples WHERE id=?',(sid,)).fetchone()
  rule['source_stale']=not current or current['id']!=rid or not sample or bool(sample['archived_at']) or bool(sample['needs_review'])
 return rule

def validate_evidence(c,rule,existing=None):
 if existing and existing['source_review_id']:
  if rule['source_sample_id']!=existing['source_sample_id']:raise ValueError('Không đổi được bình luận nguồn của nháp; tạo đề xuất mới từ mẫu khác.')
  original=existing['source_text']
 elif rule.get('source_sample_id'):
  sample=c.execute('SELECT text FROM samples WHERE id=?',(rule['source_sample_id'],)).fetchone()
  if not sample:raise ValueError('Không có bình luận nguồn.')
  original=sample['text']
 else:original=None
 if rule.get('evidence') and original is not None and rule['evidence'] not in original:raise ValueError('Bằng chứng phải là đoạn nguyên văn trong bình luận nguồn.')
 if rule['status']=='active' and rule.get('source_sample_id'):
  sid=rule['source_sample_id'];latest=c.execute('SELECT * FROM reviews WHERE sample_id=? ORDER BY revision DESC LIMIT 1',(sid,)).fetchone()
  sample=c.execute('SELECT archived_at,needs_review FROM samples WHERE id=?',(sid,)).fetchone()
  if not latest or latest['decision']!='VIOLATION' or not sample or sample['archived_at'] or sample['needs_review'] or json.loads(latest['labels_json']).get(rule['category'])!=1:raise ValueError('Nhãn nguồn chưa xác nhận vi phạm nhóm này; kiểm tra lại trước khi bật blacklist.')
  if existing and existing['source_review_id'] and existing['source_review_id']!=latest['id']:raise Conflict('Nhãn nguồn đã đổi. Tạo đề xuất từ phiên bản nhãn mới trước khi bật.')
