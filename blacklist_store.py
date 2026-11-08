"""Versioned Blacklist curation, source provenance and a scoped rule demo.

Callers own the transaction, workspace version and backup scheduling. Draft
edits never overwrite the pinned published revision used by the demo.
"""
import hashlib,json,re
from pathlib import Path
import accounts as auth
from collaboration import Conflict
import context_rules

SCHEMA=(Path(__file__).parent/'sql/008_blacklist_studio.sql').read_text(encoding='utf8')
PAGE_SIZE=30
MAX_EXAMPLES=30

def dumps(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)
def migrate(c):c.executescript(SCHEMA)
def _value(o,key,default=''):
 value=o.get(key,default)
 return value[0] if isinstance(value,list) and value else default if isinstance(value,list) else value
def _text(value,label,limit=20000):
 if not isinstance(value,str) or len(value)>limit:raise ValueError(label+' cần là văn bản, tối đa '+str(limit)+' ký tự.')
 return value.strip()
def _page(query):
 try:page=int(_value(query,'page',0))
 except (ValueError,TypeError):raise ValueError('Trang dữ liệu không hợp lệ.')
 if not 0<=page<=100000:raise ValueError('Trang dữ liệu không hợp lệ.')
 return page
def _id(value,label='Mã mục'):
 if type(value) is not int or value<=0:raise ValueError(label+' không hợp lệ.')
 return value
def _item_row(c,user,item_id,write=False):
 row=c.execute('SELECT * FROM studio_blacklist_items WHERE id=?',(_id(item_id),)).fetchone()
 if not row:raise ValueError('Không có mục Blacklist này.')
 if user['role']!='admin':
  if row['created_by_user_id']!=user['id']:raise auth.Forbidden('Bạn chỉ được xem và sửa các mục Blacklist do mình tạo.')
  if write and (row['status']!='draft' or row['published_version'] is not None):raise auth.Forbidden('Admin đã bật mục này vào kho; bạn chỉ được xem.')
 return row
def _source(c,user,sid,rid=None):
 auth.sample_access(c,user,_id(sid,'Mã bình luận'))
 sample=c.execute('SELECT * FROM samples WHERE id=?',(sid,)).fetchone()
 review=c.execute('SELECT * FROM reviews WHERE sample_id=? ORDER BY revision DESC LIMIT 1',(sid,)).fetchone()
 if not review or sample['needs_review']:raise ValueError('Bình luận cần có nhãn đã lưu và không đang bị trả lại để sửa.')
 if rid is not None and rid!=review['id']:raise Conflict('Nhãn của bình luận đã đổi. Mở lại bình luận trước khi thêm vào Blacklist.')
 if user['role']!='admin' and review['user_id']!=user['id']:raise auth.Forbidden('Chỉ thêm vào Blacklist từ các bình luận do bạn gắn nhãn trong phần việc được giao.')
 return sample,review
def _existing_source_access(c,user,sid):
 # An admin must still be able to disable or archive a rule after its source
 # was archived. Existing snapshots remain immutable and publication freshness
 # is checked separately; only new source selections require an active sample.
 if user['role']=='admin':return
 assignment=c.execute('SELECT user_id FROM task_assignments WHERE sample_id=?',(sid,)).fetchone()
 if not assignment or assignment['user_id']!=user['id']:raise auth.Forbidden('Bình luận nguồn không còn nằm trong phần việc của bạn.')
def _source_issue(c,example,category):
 sid=example.get('source_sample_id');rid=example.get('source_review_id')
 if not sid or not rid:return None
 sample=c.execute('SELECT * FROM samples WHERE id=?',(sid,)).fetchone()
 latest=c.execute('SELECT * FROM reviews WHERE sample_id=? ORDER BY revision DESC LIMIT 1',(sid,)).fetchone()
 if not sample:return 'Bình luận nguồn không còn; cần kiểm tra lại ví dụ liên kết.'
 if sample['archived_at']:return 'Bình luận nguồn đã xóa, hoàn tác hoặc thay thế; cần kiểm tra lại mục trước khi chặn.'
 if sample['needs_review']:return 'Nhãn của bình luận đang bị trả lại để sửa; mục này chỉ nhắc người duyệt trong lúc chờ kiểm tra.'
 if not latest or latest['id']!=rid:return 'Nhãn nguồn đã có phiên bản mới; cần kiểm tra lại ví dụ liên kết.'
 if sample['text']!=example['text'] or sample['context']!=example.get('context',''):return 'Nội dung nguồn đã đổi; cần kiểm tra lại ví dụ liên kết.'
 labels=json.loads(latest['labels_json'])
 wanted=1 if example.get('role')=='violation' else 0
 if labels.get(category)!=wanted:return 'Nhãn đã lưu của bình luận không phù hợp với cách bạn dùng câu này. Kiểm tra lại nhãn và câu ví dụ.'
 if wanted==1 and latest['decision']!='VIOLATION':return 'Nhãn nguồn chưa xác nhận vi phạm.'
 return None
def _load(c,row,full=True):
 result={k:row[k] for k in ['id','name','category','match_type','mode','status','version','created_by_user_id','created_at','updated_by_user_id','updated_at','published_version','published_at']}
 result['config']=json.loads(row['config_json']);result['has_pending_changes']=row['published_version'] is not None and row['published_version']!=row['version']
 examples=[]
 for source in c.execute('SELECT * FROM studio_blacklist_examples WHERE item_id=? ORDER BY id',(row['id'],)):
  e=dict(source);e.pop('item_id');e.pop('created_at');e['source_labels']=json.loads(e.pop('source_labels_json'));issue=_source_issue(c,e,row['category']);e['source_stale']=bool(issue);e['source_warning']=issue;examples.append(e)
 result['example_count']=len(examples);result['violation_count']=sum(e['role']=='violation' for e in examples);result['counterexample_count']=sum(e['role']=='counterexample' for e in examples);result['source_stale']=any(e['source_stale'] for e in examples)
 if full:result['examples']=examples
 return result
def count_stats(c,user):
 where='' if user['role']=='admin' else ' WHERE created_by_user_id=?';args=[] if not where else [user['id']]
 counts={name:0 for name in ['draft','published','disabled','archived']}
 for row in c.execute('SELECT status,COUNT(*) AS n FROM studio_blacklist_items'+where+' GROUP BY status',args):counts[row['status']]=row['n']
 counts['live']=c.execute("SELECT COUNT(*) FROM studio_blacklist_items WHERE published_version IS NOT NULL AND status NOT IN ('disabled','archived')").fetchone()[0]
 return counts
def list_items(c,user,query=None):
 query=query or {};page=_page(query);where=[];args=[]
 if user['role']!='admin':where.append('created_by_user_id=?');args.append(user['id'])
 status=_value(query,'status','all')
 if status not in ['all','draft','published','disabled','archived']:raise ValueError('Trạng thái lọc không hợp lệ.')
 if status!='all':where.append('status=?');args.append(status)
 category=_value(query,'category','');q=_text(_value(query,'q',''),'Tìm kiếm',200)
 if category:where.append('category=?');args.append(category)
 if q:where.append('name LIKE ?');args.append('%'+q+'%')
 clause=' WHERE '+' AND '.join(where) if where else ''
 total=c.execute('SELECT COUNT(*) FROM studio_blacklist_items'+clause,args).fetchone()[0]
 items=[_load(c,r,False) for r in c.execute('SELECT * FROM studio_blacklist_items'+clause+' ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?',args+[PAGE_SIZE,page*PAGE_SIZE])]
 return {'items':items,'total':total,'page':page,'page_size':PAGE_SIZE,'counts':count_stats(c,user)}
def get_item(c,user,item_id):return _load(c,_item_row(c,user,item_id))
def sources(c,user,query=None):
 query=query or {};page=_page(query);where=['s.archived_at IS NULL','s.needs_review=0','r.id IS NOT NULL'];args=[]
 if user['role']!='admin':where+=['a.user_id=?','r.user_id=?'];args+=[user['id'],user['id']]
 decision=_value(query,'decision','')
 if decision and decision!='all':
  if decision not in ['ALLOW','VIOLATION','UNSURE']:raise ValueError('Kết luận lọc không hợp lệ.')
  where.append('r.decision=?');args.append(decision)
 category=_value(query,'category','')
 if category:
  if not c.execute('SELECT 1 FROM categories WHERE code=?',(category,)).fetchone():raise ValueError('Nhóm vi phạm không tồn tại.')
  where.append("json_extract(r.labels_json,?) IS NOT NULL");args.append('$."'+category+'"')
 q=_text(_value(query,'q',''),'Tìm kiếm',200)
 if q:where.append('(s.text LIKE ? OR CAST(s.id AS TEXT)=?)');args+=['%'+q+'%',q]
 marked=_value(query,'marked','')
 if marked in [True,1,'1','true']:
  if user['role']=='admin':where.append('EXISTS(SELECT 1 FROM studio_curation_bookmarks b WHERE b.sample_id=s.id)')
  else:where.append('EXISTS(SELECT 1 FROM studio_curation_bookmarks b WHERE b.sample_id=s.id AND b.user_id=?)');args.append(user['id'])
 joins=' FROM samples s LEFT JOIN task_assignments a ON a.sample_id=s.id LEFT JOIN reviews r ON r.id=(SELECT r2.id FROM reviews r2 WHERE r2.sample_id=s.id ORDER BY r2.revision DESC LIMIT 1)'
 clause=' WHERE '+' AND '.join(where)
 total=c.execute('SELECT COUNT(*)'+joins+clause,args).fetchone()[0];result=[]
 for row in c.execute('SELECT s.*,r.id AS review_id,r.revision,r.decision,r.labels_json,r.user_id AS reviewer_user_id'+joins+clause+' ORDER BY r.id DESC LIMIT ? OFFSET ?',args+[PAGE_SIZE,page*PAGE_SIZE]):
  data={k:row[k] for k in ['id','text','context','source','synthetic']};data['review']={'id':row['review_id'],'revision':row['revision'],'decision':row['decision'],'labels':json.loads(row['labels_json']),'user_id':row['reviewer_user_id']}
  bookmark=c.execute('SELECT * FROM studio_curation_bookmarks WHERE sample_id=?'+('' if user['role']=='admin' else ' AND user_id=?')+' ORDER BY created_at DESC LIMIT 1',[row['id']]+([] if user['role']=='admin' else [user['id']])).fetchone()
  data['marked']=bool(bookmark);data['candidate_evidence']=bookmark['candidate_evidence'] if bookmark else '';data['bookmark_evidence']=data['candidate_evidence'];data['bookmark_stale']=bool(bookmark and bookmark['review_id']!=row['review_id']);result.append(data)
 return {'sources':result,'total':total,'page':page,'page_size':PAGE_SIZE}
def bookmark(c,user,o,stamp):
 sid=_id(o.get('sample_id'),'Mã bình luận');sample,review=_source(c,user,sid,o.get('review_id'));marked=o.get('marked',True)
 if type(marked) is not bool:raise ValueError('Trạng thái đánh dấu phải là true/false.')
 evidence=_text(o.get('candidate_evidence',''),'Đoạn đã chọn')
 if evidence and evidence not in sample['text']:raise ValueError('Đoạn đã chọn phải nằm nguyên văn trong bình luận nguồn.')
 if marked:c.execute('INSERT INTO studio_curation_bookmarks(user_id,sample_id,review_id,candidate_evidence,created_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,sample_id) DO UPDATE SET review_id=excluded.review_id,candidate_evidence=excluded.candidate_evidence,created_at=excluded.created_at',(user['id'],sid,review['id'],evidence,stamp))
 else:c.execute('DELETE FROM studio_curation_bookmarks WHERE user_id=? AND sample_id=?',(user['id'],sid))
 return {'marked':marked,'sample_id':sid,'review_id':review['id']}
def _examples(c,user,o,category,old=None,imported=False):
 rows=o.get('examples',[])
 if not isinstance(rows,list) or len(rows)>MAX_EXAMPLES:raise ValueError('Tối đa '+str(MAX_EXAMPLES)+' ví dụ mỗi mục.')
 existing={e['id']:e for e in (old or {}).get('examples',[])};clean=[];seen=set()
 for raw in rows:
  if not isinstance(raw,dict):raise ValueError('Ví dụ không hợp lệ.')
  prior=existing.get(raw.get('id'));sid=raw.get('source_sample_id') or None;rid=raw.get('source_review_id') or None
  if prior and prior['source_kind']=='sample':
   if sid!=prior['source_sample_id'] or rid!=prior['source_review_id']:raise ValueError('Không đổi liên kết nguồn của ví dụ đã lưu. Xóa ví dụ và chọn nguồn mới nếu cần.')
  text=_text(raw.get('text',''),'Nội dung ví dụ');context=_text(raw.get('context',''),'Ngữ cảnh ví dụ')
  expected=raw.get('expected','MATCH');role=raw.get('role') or ('violation' if expected=='MATCH' else 'counterexample')
  if expected not in ['MATCH','REVIEW','NO_MATCH'] or role not in ['violation','counterexample']:raise ValueError('Chọn cách xử lý cho mỗi câu ví dụ: Chặn, Cần người xem hoặc Cho đi tiếp.')
  if role=='counterexample' and expected=='MATCH':raise ValueError('Câu này đang được lưu là không vi phạm. Chọn Cần người xem hoặc Cho đi tiếp; kiểm tra lại nhãn gốc nếu bạn muốn chặn.')
  kind='imported' if imported else 'manual';labels={}
  if sid:
   _id(sid,'Mã bình luận');_id(rid,'Mã nhãn nguồn')
   if prior and prior['source_kind']=='sample':
    if text!=prior['text'] or context!=prior['context']:raise ValueError('Giữ nguyên câu và ngữ cảnh nguồn của ví dụ đã lưu.')
    # A stale snapshot remains editable as a draft but cannot be published.
    _existing_source_access(c,user,sid);labels=prior.get('source_labels',{});kind='sample'
   else:
    sample,review=_source(c,user,sid,rid)
    if text and text!=sample['text'] or context and context!=sample['context']:raise ValueError('Ví dụ liên kết cần giữ toàn bộ câu và ngữ cảnh nguồn nguyên văn.')
    text=sample['text'];context=sample['context'];labels=json.loads(review['labels_json']);kind='sample'
  elif rid:raise ValueError('Nhãn nguồn cần đi kèm bình luận nguồn.')
  elif prior and prior['source_kind']=='imported':kind='imported'
  if not text:raise ValueError('Nhập nội dung ví dụ hoặc chọn bình luận nguồn.')
  key=(text,context)
  if key in seen:raise ValueError('Có hai câu ví dụ giống nhau. Xóa bớt một câu rồi chọn cách xử lý cho câu còn lại.')
  seen.add(key);clean.append({'text':text,'context':context,'expected':expected,'role':role,'source_kind':kind,'source_sample_id':sid,'source_review_id':rid,'source_labels':labels})
 return clean
def _definition(c,user,o,old=None,imported=False):
 clean=context_rules.validate_definition(o)
 if not c.execute('SELECT 1 FROM categories WHERE code=?',(clean['category'],)).fetchone():raise ValueError('Nhóm vi phạm không tồn tại.')
 clean['examples']=_examples(c,user,o,clean['category'],old,imported)
 return clean
def _fingerprint(item):
 cfg=dict(item['config'])
 if item['match_type']=='combined':
  for key in ['topics','actions']:cfg[key]=sorted(set(context_rules.normalize(term) for term in cfg[key]))
 elif item['match_type']=='phrase':cfg['pattern']=context_rules.normalize(cfg['pattern'])
 return hashlib.sha256(dumps({'category':item['category'],'match_type':item['match_type'],'config':cfg}).encode()).hexdigest()
def _tests(item):return context_rules.evaluate_examples(item)
def _publication(c,item,tests):
 if not any(e['expected']=='MATCH' and e['role']=='violation' for e in item['examples']):raise ValueError('Cần thêm một câu bạn muốn chặn rồi chọn Chặn. Ví dụ: Vào nhóm cá cược nhận thưởng ngay.')
 if not any(e['expected']=='NO_MATCH' and e['role']=='counterexample' for e in item['examples']):raise ValueError('Cần thêm một câu bạn muốn cho đi tiếp rồi chọn Cho đi tiếp. Ví dụ: Chúc mọi người một ngày vui vẻ.')
 if not all(t['passed'] for t in tests):raise ValueError('Có câu đang ra cách xử lý khác điều bạn chọn. Bấm Thử các câu mẫu, xem Bạn muốn và Hệ thống khi bật chặn, rồi sửa các từ cần tìm. Giữ cách xử lý theo ý bạn muốn; không cần chọn theo kết quả máy.')
 for example in item['examples']:
  issue=_source_issue(c,example,item['category'])
  if issue:raise Conflict(issue)
def save_item(c,user,o,stamp,_imported=False):
 if not isinstance(o,dict):raise ValueError('Mục Blacklist không hợp lệ.')
 iid=o.get('id');row=_item_row(c,user,iid,True) if iid else None;old=_load(c,row) if row else None
 if row and o.get('version')!=row['version']:raise Conflict('Mục vừa được người khác cập nhật. Tải lại để gộp; bản nháp của bạn vẫn được giữ.')
 item=_definition(c,user,o,old,_imported);status=item.get('status','draft')
 if user['role']!='admin' and status!='draft':raise auth.Forbidden('Thành viên chỉ được lưu nháp. Admin mới được bật hoặc tắt mục trong kho.')
 if status not in ['draft','published','disabled','archived']:raise ValueError('Trạng thái mục không hợp lệ.')
 tests=_tests(item)
 if status=='published':_publication(c,item,tests)
 version=(row['version']+1) if row else 1;fp=_fingerprint(item);owner=row['created_by_user_id'] if row else user['id']
 duplicate=c.execute('SELECT id FROM studio_blacklist_items WHERE created_by_user_id=? AND definition_hash=? AND id<>?',(owner,fp,iid or -1)).fetchone()
 if duplicate:raise Conflict('Đã có mục tương tự #'+str(duplicate['id'])+'. Mở mục đó để bổ sung ví dụ thay vì tạo trùng.')
 values=(item['name'],item['category'],item['match_type'],item['mode'],status,version,dumps(item['config']),fp,user['id'],stamp)
 if row:c.execute('UPDATE studio_blacklist_items SET name=?,category=?,match_type=?,mode=?,status=?,version=?,config_json=?,definition_hash=?,updated_by_user_id=?,updated_at=? WHERE id=?',values+(iid,))
 else:iid=c.execute('INSERT INTO studio_blacklist_items(name,category,match_type,mode,status,version,config_json,definition_hash,updated_by_user_id,updated_at,created_by_user_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',values+(user['id'],stamp)).lastrowid
 if row and row['status'] in ['disabled','archived'] and status=='draft':c.execute('UPDATE studio_blacklist_items SET published_version=NULL,published_snapshot_json=NULL,published_at=NULL WHERE id=?',(iid,))
 c.execute('DELETE FROM studio_blacklist_examples WHERE item_id=?',(iid,))
 for e in item['examples']:c.execute('INSERT INTO studio_blacklist_examples(item_id,text,context,expected,role,source_kind,source_sample_id,source_review_id,source_labels_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(iid,e['text'],e['context'],e['expected'],e['role'],e['source_kind'],e['source_sample_id'],e['source_review_id'],dumps(e['source_labels']),stamp))
 current=_load(c,c.execute('SELECT * FROM studio_blacklist_items WHERE id=?',(iid,)).fetchone())
 if status=='published':
  current['published_version']=version;current['published_at']=stamp;current['has_pending_changes']=False
  c.execute('UPDATE studio_blacklist_items SET published_version=?,published_snapshot_json=?,published_at=? WHERE id=?',(version,dumps(current),stamp,iid))
 c.execute('INSERT INTO studio_blacklist_history(item_id,version,snapshot_json,actor_user_id,created_at) VALUES(?,?,?,?,?)',(iid,version,dumps(current),user['id'],stamp))
 return {'item':current,'tests':tests}
def history(c,user,item_id):
 _item_row(c,user,item_id)
 rows=[]
 for row in c.execute('SELECT version,actor_user_id,created_at,snapshot_json FROM studio_blacklist_history WHERE item_id=? ORDER BY version DESC LIMIT 100',(item_id,)):
  d=dict(row);d['snapshot']=json.loads(d.pop('snapshot_json'));rows.append(d)
 return {'history':rows}
def _draft_scope(key,client_id):
 if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_.:~-]{1,120}',key):raise ValueError('Mã bản nháp không hợp lệ.')
 if not isinstance(client_id,str) or client_id and not re.fullmatch(r'[a-f0-9]{32,64}',client_id):raise ValueError('Mã phiên bản nháp không hợp lệ.')
 return key,client_id
def get_editor_draft(c,user,key,client_id=''):
 key,client_id=_draft_scope(key,client_id)
 row=c.execute('SELECT payload_json,updated_at FROM studio_editor_drafts WHERE user_id=? AND client_id=? AND draft_key=?',(user['id'],client_id,key)).fetchone()
 return {'draft':{'key':key,'payload':json.loads(row['payload_json']),'updated_at':row['updated_at']} if row else None}
def save_editor_draft(c,user,o,stamp):
 key,client_id=_draft_scope(o.get('key'),o.get('client_id',''));payload=o.get('payload',o.get('draft'))
 if not isinstance(payload,dict):raise ValueError('Nội dung bản nháp cần là một object.')
 encoded=dumps(payload)
 if len(encoded.encode())>100*1024:raise ValueError('Bản nháp tối đa 100 KiB.')
 old=c.execute('SELECT payload_json FROM studio_editor_drafts WHERE user_id=? AND client_id=? AND draft_key=?',(user['id'],client_id,key)).fetchone()
 if old and old['payload_json']==encoded:return {'draft_saved':True,'changed':False,'key':key}
 c.execute('INSERT INTO studio_editor_drafts(user_id,client_id,draft_key,payload_json,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id,client_id,draft_key) DO UPDATE SET payload_json=excluded.payload_json,updated_at=excluded.updated_at',(user['id'],client_id,key,encoded,stamp))
 return {'draft_saved':True,'changed':True,'key':key}
def delete_editor_draft(c,user,o):
 key,client_id=_draft_scope(o.get('key'),o.get('client_id',''))
 removed=c.execute('DELETE FROM studio_editor_drafts WHERE user_id=? AND client_id=? AND draft_key=?',(user['id'],client_id,key)).rowcount
 return {'deleted':bool(removed),'key':key}
def preview(c,user,o):
 if o.get('item_id'):
  item=get_item(c,user,o['item_id'])
 else:
  raw=o.get('item')
  if not isinstance(raw,dict):raise ValueError('Chọn một mục hoặc nhập điều kiện để chạy thử.')
  old=get_item(c,user,raw['id']) if raw.get('id') else None
  item=_definition(c,user,raw,old)
 tests=_tests(item);text=_text(o.get('text',''),'Bình luận thử');context=_text(o.get('context',''),'Ngữ cảnh thử')
 simulated=dict(item,status='published');result=context_rules.evaluate_bank([simulated],text,context) if text else None
 if result:
  result['scope_note']='Đang thử riêng mục bạn đang mở. Thay đổi ở đây chỉ vào kho khi admin bấm Bật vào kho.'
 return {'item':item,'tests':tests,'result':result,'preview':True}
def _published_items(c):
 """Resolve source freshness against the pinned revision, also for exports.

 Exporting a stale block snapshot unmodified would let an offline demo block
 while the server correctly downgraded it to a signal.  Both use this resolver.
 """
 rows=c.execute("SELECT published_snapshot_json FROM studio_blacklist_items WHERE published_version IS NOT NULL AND status NOT IN ('disabled','archived') ORDER BY id");items=[]
 for row in rows:
  item=json.loads(row['published_snapshot_json']);item['status']='published'
  issues=[_source_issue(c,e,item['category']) for e in item.get('examples',[])];issues=[i for i in issues if i]
  item['source_stale']=bool(issues);item['source_warnings']=list(dict.fromkeys(issues))
  if issues:
   item['configured_mode']=item['mode'];item['mode']='signal'
  items.append(item)
 return items
def demo(c,user,o):
 text=_text(o.get('text',''),'Bình luận thử');context=_text(o.get('context',''),'Ngữ cảnh thử')
 if not text:raise ValueError('Nhập một bình luận để thử Blacklist.')
 items=_published_items(c);stale={item['id']:item['source_warnings'] for item in items if item['source_stale']}
 result=context_rules.evaluate_bank(items,text,context)
 for match in result.get('matches',[]):
  rule_id=match.get('rule_id',match.get('id'))
  if rule_id in stale:
   match.setdefault('reasons',[]).extend(stale[rule_id]);match.setdefault('ambiguities',[]).append('source_changed')
 result['published_count']=len(items);result['pending_count']=count_stats(c,user)['draft'];result['stale_rule_count']=len(stale)
 result['scope_note']='Chỉ thử các mục đang bật trong kho. Cho đi tiếp nghĩa là qua bước Blacklist để kiểm tra tiếp; demo chưa chạy fastText, ViSoBERT hoặc PhoBERT.'
 return result
def export_pack(c,user):
 auth.admin(user);items=[_load(c,row) for row in c.execute('SELECT * FROM studio_blacklist_items ORDER BY id')]
 return {'schema_version':2,'format':'blacklist-studio-items','scope':'curation_and_published_snapshots','items':items,'published_items':_published_items(c)}
def import_pack(c,user,o,stamp):
 auth.admin(user);pack=o.get('pack',o)
 if not isinstance(pack,dict):raise ValueError('File kho Blacklist không hợp lệ.')
 if pack.get('schema_version',2)!=2:raise ValueError('Phiên bản file kho không được hỗ trợ; cần schema_version 2.')
 rows=pack.get('items')
 if not isinstance(rows,list) or not 0<len(rows)<=100:raise ValueError('Nhập từ 1 đến 100 mục mỗi lần.')
 prepared=[];seen={r['definition_hash'] for r in c.execute('SELECT definition_hash FROM studio_blacklist_items WHERE created_by_user_id=?',(user['id'],))};duplicates=0
 for raw in rows:
  if not isinstance(raw,dict):raise ValueError('Mục nhập không hợp lệ.')
  if not isinstance(raw.get('examples',[]),list) or any(not isinstance(e,dict) for e in raw.get('examples',[])):raise ValueError('Danh sách ví dụ trong file không hợp lệ.')
  item={k:v for k,v in raw.items() if k not in ['id','version','published_version','published_snapshot_json','published_at']};item.update(status='draft',mode='signal')
  item['examples']=[{k:v for k,v in e.items() if k not in ['id','source_sample_id','source_review_id']} for e in raw.get('examples',[])]
  clean=_definition(c,user,item,imported=True);fp=_fingerprint(clean)
  if fp in seen:duplicates+=1;continue
  seen.add(fp);prepared.append(clean)
 created=[]
 for item in prepared:
  result=save_item(c,user,item,stamp,_imported=True);created.append(result['item']['id'])
 return {'added':len(created),'duplicates':duplicates,'ids':created,'status':'draft','mode':'signal'}
