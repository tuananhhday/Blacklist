"""Local manual annotation studio. Python 3.10+, standard library only."""
import base64, hmac
import csv, hashlib, io, json, os, re, sqlite3, unicodedata, uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('STUDIO_DATA',str(ROOT/'data')))
EXPORTS=Path(os.environ.get('STUDIO_EXPORTS',str(ROOT/'exports')))
CATEGORIES=dict(zip(['co_bac','lua_dao','spam','thu_ghet_xuc_pham','khieu_dam_bao_luc','hang_cam','tin_gia','an_ninh_chinh_tri','hai_tre_em'],['Cờ bạc','Lừa đảo','Spam','Thù ghét, xúc phạm','Khiêu dâm, bạo lực','Hàng cấm','Tin giả','An ninh, chính trị','Gây hại trẻ em']))
TOKEN=uuid.uuid4().hex
PASSWORD=os.environ.get('STUDIO_PASSWORD','')
USERNAME=os.environ.get('STUDIO_USERNAME','admin')

def now(): return datetime.now(timezone.utc).isoformat()
def dumps(v): return json.dumps(v,ensure_ascii=False,allow_nan=False)
def norm(s): return re.sub(r'\s+',' ',unicodedata.normalize('NFC',s)).strip().casefold()
def connect():
 c=sqlite3.connect(DATA/'studio.sqlite3');c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c

def init():
 DATA.mkdir(parents=True,exist_ok=True);EXPORTS.mkdir(parents=True,exist_ok=True)
 with connect() as c:
  c.executescript((ROOT/'sql/schema.sql').read_text(encoding='utf8'))
  c.executemany('INSERT OR IGNORE INTO categories VALUES(?,?)',CATEGORIES.items())

def require(ok,msg):
 if not ok: raise ValueError(msg)
def field(o,k,maximum=20000,required=False):
 s=o.get(k,'');require(isinstance(s,str),f'{k}: cần chuỗi văn bản');s=s.strip();require(len(s)<=maximum,f'{k}: quá dài');require(not required or bool(s),f'Thiếu {k}');return s

def contains(text,phrase):
 return bool(re.search(r'(?<!\w)'+re.escape(norm(phrase))+r'(?!\w)',norm(text)))

def evaluate(rule,text):
 cfg=rule['config'];kind=rule['kind'];matches=[]
 if kind=='exact':
  if norm(text)==norm(cfg['pattern']): matches=[text]
 elif kind in ('url','domain'):
  urls=re.findall(r'https?://[^\s<>"\']+',text,re.I)
  target=cfg['pattern'].casefold().rstrip('/')
  def url_key(value):
   part=urlsplit(value)
   return (part.scheme.casefold(),part.netloc.casefold(),part.path or '/',part.query)
  for u in urls:
   u=u.rstrip('.,;!?)')
   if kind=='url' and url_key(u)==url_key(cfg['pattern']):matches.append(u)
   if kind=='domain' and (urlsplit(u).hostname or '').casefold()==target:matches.append(u)
 else:
  for sentence in re.split(r'[.!?;\n]+',text):
   aa=[x for x in cfg['topic'] if contains(sentence,x)]
   bb=[x for x in cfg['behavior'] if contains(sentence,x)]
   if aa and bb:
    context=[x for x in cfg['context'] if contains(sentence,x)]
    matches.append({'topic':aa,'behavior':bb,'context':context})
 if not matches:return {'result':'NO_MATCH','evidence':[]}
 contextual=kind=='combined' and any(x['context'] for x in matches)
 return {'result':'CONTEXT_REVIEW' if contextual else 'MATCH','evidence':matches,
         'action':'REVIEW','note':'Chỉ là tín hiệu, không kết luận ý định hoặc tự động chặn.'}

def validate_rule(o):
 name=field(o,'name',200,True);category=field(o,'category',100,True);kind=field(o,'kind',30,True)
 require(category in CATEGORIES,'Nhãn không tồn tại');require(kind in ['exact','combined','url','domain'],'Kiểu luật không hợp lệ')
 cfg=o.get('config',{});require(isinstance(cfg,dict),'Điều kiện không hợp lệ')
 if kind=='combined':
  cfg={k:cfg.get(k,[]) for k in ['topic','behavior','context']}
  for k,v in cfg.items(): require(isinstance(v,list) and len(v)<=100 and all(isinstance(x,str) and 0<len(x.strip())<=200 for x in v),'Danh sách dấu hiệu không hợp lệ')
  require(cfg['topic'] and cfg['behavior'],'Cần dấu hiệu chủ đề và hành vi')
 else:
  cfg={'pattern':field(cfg,'pattern',20000,True)}
  if kind=='url':require(urlsplit(cfg['pattern']).scheme in ('http','https') and bool(urlsplit(cfg['pattern']).hostname),'URL cần có http:// hoặc https://')
  if kind=='domain':require(bool(re.fullmatch(r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',cfg['pattern'])),'Chỉ nhập tên miền, không có https:// hoặc đường dẫn')
 tests=o.get('tests',[]);require(isinstance(tests,list) and len(tests)<=100,'Danh sách kiểm tra không hợp lệ')
 clean=[]
 for t in tests:
  text=field(t,'text',20000,True);expected=field(t,'expected',30,True)
  require(expected in ['MATCH','NO_MATCH','CONTEXT_REVIEW'],'Kết quả mong muốn không hợp lệ');clean.append({'text':text,'expected':expected})
 rule={'name':name,'category':category,'kind':kind,'config':cfg,'tests':clean,
       'status':field(o,'status',30,True),'reviewer':field(o,'reviewer',100,True),'reason':field(o,'reason',2000,True),'source_sample_id':o.get('source_sample_id') or None}
 require(rule['status'] in ['draft','active','disabled'],'Trạng thái không hợp lệ')
 results=[dict(t,actual=evaluate(rule,t['text'])['result']) for t in clean]
 if rule['status']=='active':
  require(any(t['expected']=='MATCH' for t in clean) and any(t['expected'] in ['NO_MATCH','CONTEXT_REVIEW'] for t in clean),'Để bật: cần ít nhất mẫu bắt được và mẫu đối chiếu')
  require(all(t['actual']==t['expected'] for t in results),'Có câu kiểm tra chưa đạt')
 return rule,results

def state(c):
 samples=[]
 for r in c.execute('SELECT * FROM samples ORDER BY id DESC'):
  s=dict(r);rr=c.execute('SELECT * FROM reviews WHERE sample_id=? ORDER BY revision DESC LIMIT 1',(s['id'],)).fetchone()
  s['review']=dict(rr) if rr else None
  if rr:s['review']['labels']=json.loads(rr['labels_json'])
  samples.append(s)
 rules=[]
 for r in c.execute('SELECT * FROM rules ORDER BY id DESC'):
  x=dict(r);x['config']=json.loads(x.pop('config_json'));x['tests']=json.loads(x.pop('tests_json'));rules.append(x)
 return {'categories':CATEGORIES,'samples':samples,'rules':rules}

def atomic(path,text):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(text,encoding='utf8');tmp.replace(path)
def export_all(c):
 s=state(c);stamp=now()
 atomic(EXPORTS/'blacklist.json',dumps({'schema_version':1,'exported_at':stamp,'normalization':'NFC, whitespace, casefold; preserve accents','action':'REVIEW','rules':[r for r in s['rules'] if r['status']=='active']}))
 atomic(EXPORTS/'blacklist_drafts.json',dumps({'exported_at':stamp,'rules':s['rules']}))
 training=[]
 for sample in s['samples']:
  r=sample['review']
  if r and r['decision']!='UNSURE':
   training.append({'id':sample['id'],'text':sample['text'],'context':sample['context'],'source':sample['source'],'synthetic':bool(sample['synthetic']),'text_hash':sample['fingerprint'],'review_id':r['id'],'review_revision':r['revision'],'policy_version':r['policy_version'],'labels':r['labels'],'label_mask':{k:int(v is not None) for k,v in r['labels'].items()},'intent':r['intent'],'evidence':r['evidence'],'reason':r['reason']})
 atomic(EXPORTS/'training_data.jsonl',''.join(dumps(x)+'\n' for x in training))
 atomic(EXPORTS/'backup.sql','\n'.join(c.iterdump()))


def import_blacklist(c,o):
 rows=o.get('rules');require(isinstance(rows,list) and 0<len(rows)<=1000,'Cần 1–1000 mục blacklist')
 reviewer=field(o,'reviewer',100,True)
 known={(r['category'],r['kind'],dumps(json.loads(r['config_json']))) for r in c.execute('SELECT * FROM rules')}
 prepared=[];duplicates=0
 for i,row in enumerate(rows):
  require(isinstance(row,dict),f'Mục {i+1}: cần object')
  try:
   r,_=validate_rule(dict(row,status='draft',reviewer=reviewer,source_sample_id=None,reason=row.get('reason') or 'Nhập từ file blacklist'))
  except (ValueError,TypeError,KeyError) as e:raise ValueError(f'Mục {i+1}: {e}')
  key=(r['category'],r['kind'],dumps(r['config']))
  if key in known:duplicates+=1;continue
  known.add(key);prepared.append(r)
 if not o.get('preview',True):
  for r in prepared:
   args=(r['name'],r['category'],r['kind'],dumps(r['config']),dumps(r['tests']),'draft',1,None,reviewer,r['reason'],now())
   rid=c.execute('INSERT INTO rules(name,category,kind,config_json,tests_json,status,version,source_sample_id,reviewer,reason,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',args).lastrowid
   c.execute('INSERT INTO rule_history(rule_id,version,snapshot_json,created_at) VALUES(?,?,?,?)',(rid,1,dumps(dict(r,id=rid,version=1,action='REVIEW')),now()))
 return {'preview':o.get('preview',True),'added':len(prepared),'duplicates':duplicates,'items':[{'name':r['name'],'kind':r['kind'],'category':r['category']} for r in prepared]}

class Handler(BaseHTTPRequestHandler):
 def setup(self):
  super().setup();self.connection.settimeout(20)
 def authorized(self):
  if not PASSWORD:return True
  expected='Basic '+base64.b64encode((USERNAME+':'+PASSWORD).encode()).decode()
  if hmac.compare_digest(self.headers.get('Authorization',''),expected):return True
  self.send_response(401);self.send_header('WWW-Authenticate','Basic realm="Blacklist Studio", charset="UTF-8"');self.send_header('Content-Length','0');self.end_headers();return False

 def reply(self,obj,status=200,ctype='application/json; charset=utf-8',filename=None):
  data=(dumps(obj) if ctype.startswith('application/json') else obj).encode('utf8')
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
  if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
  self.end_headers();self.wfile.write(data)
 def do_GET(self):
  path=urlsplit(self.path).path
  if path=='/health':return self.reply({'status':'ok'})
  if not self.authorized():return
  try:
   if path=='/api/state':
    with connect() as c:self.reply(state(c))
   elif path=='/api/session':self.reply({'token':TOKEN})
   elif path=='/api/history':
    with connect() as c:self.reply({'reviews':[dict(r) for r in c.execute('SELECT * FROM reviews ORDER BY id DESC LIMIT 500')],'rules':[dict(r) for r in c.execute('SELECT * FROM rule_history ORDER BY id DESC LIMIT 500')]})
   elif path.startswith('/export/'):
    filename=path.rsplit('/',1)[-1];require(filename in ['blacklist.json','blacklist_drafts.json','training_data.jsonl','backup.sql'],'File không hợp lệ')
    with connect() as c:export_all(c)
    self.reply((EXPORTS/filename).read_text(encoding='utf8'),ctype='text/plain; charset=utf-8',filename=filename)
   elif path in ['/','/app.js','/style.css']:
    file={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]
    ct={'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8'}[path]
    self.reply((ROOT/'static'/file).read_text(encoding='utf8'),ctype=ct)
   else:self.reply({'error':'Không tìm thấy'},404)
  except ValueError as e:self.reply({'error':str(e)},400)
 def do_POST(self):
  if not self.authorized():return
  try:
   require(self.headers.get('X-Studio-Token')==TOKEN,'Phiên hết hạn. Tải lại trang.')
   n=int(self.headers.get('Content-Length','0'));require(0<n<=2_000_000,'Yêu cầu quá lớn hoặc rỗng')
   o=json.loads(self.rfile.read(n));require(isinstance(o,dict),'Cần JSON object');path=urlsplit(self.path).path
   with connect() as c:
    if path=='/api/blacklist/import':
     result=import_blacklist(c,o)
    elif path=='/api/import':
     rows=o.get('rows',[]);require(isinstance(rows,list) and 0<len(rows)<=1000,'Mỗi lần nhập 1–1000 mẫu');added=0
     for row in rows:
      text=field(row,'text',20000,True);context=field(row,'context');source=field(row,'source',500,True);synthetic=row.get('synthetic',True)
      require(isinstance(synthetic,bool),'synthetic cần true/false')
      fp=hashlib.sha256((norm(text)+'\x00'+norm(context)).encode()).hexdigest()
      cur=c.execute('INSERT OR IGNORE INTO samples(text,context,source,synthetic,fingerprint,created_at) VALUES(?,?,?,?,?,?)',(text,context,source,int(synthetic),fp,now()));added+=cur.rowcount
     result={'added':added,'duplicates':len(rows)-added}
    elif path=='/api/review':
     sid=o.get('sample_id');sample=c.execute('SELECT * FROM samples WHERE id=?',(sid,)).fetchone();require(sample is not None,'Không có mẫu')
     previous=c.execute('SELECT MAX(revision) FROM reviews WHERE sample_id=?',(sid,)).fetchone()[0] or 0
     require(o.get('base_revision',0)==previous,'Mẫu đã thay đổi ở cửa sổ khác. Tải lại trước khi lưu.')
     decision=field(o,'decision',30,True);require(decision in ['ALLOW','VIOLATION','UNSURE'],'Quyết định không hợp lệ')
     labels=o.get('labels',{});require(isinstance(labels,dict) and set(labels)==set(CATEGORIES),'Cần đủ 9 trường nhãn')
     require(all(v is None or type(v) is int and v in [0,1] for v in labels.values()),'Nhãn phải là 0, 1 hoặc null')
     if decision=='VIOLATION':require(1 in labels.values(),'Vi phạm cần ít nhất một nhãn Có')
     if decision=='ALLOW':require(1 not in labels.values() and 0 in labels.values(),'Hợp lệ cần ít nhất một nhóm đã kiểm tra Không')
     evidence=field(o,'evidence');require(not evidence or evidence in sample['text'],'Bằng chứng phải là đoạn có trong câu gốc')
     reviewer=field(o,'reviewer',100,True);reason=field(o,'reason',2000,True);intent=field(o,'intent',100)
     c.execute('INSERT INTO reviews(sample_id,revision,decision,labels_json,intent,evidence,reason,reviewer,policy_version,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(sid,previous+1,decision,dumps(labels),intent,evidence,reason,reviewer,'demo-1',now()));result={'saved':True}
    elif path=='/api/rule':
     r,tests=validate_rule(o);rid=o.get('id');version=1
     if rid:
      old=c.execute('SELECT version FROM rules WHERE id=?',(rid,)).fetchone();require(old is not None,'Không có luật');require(o.get('version')==old[0],'Luật đã thay đổi. Tải lại.');version=old[0]+1
     args=(r['name'],r['category'],r['kind'],dumps(r['config']),dumps(r['tests']),r['status'],version,r['source_sample_id'],r['reviewer'],r['reason'],now())
     if rid:c.execute('UPDATE rules SET name=?,category=?,kind=?,config_json=?,tests_json=?,status=?,version=?,source_sample_id=?,reviewer=?,reason=?,updated_at=? WHERE id=?',args+(rid,))
     else:rid=c.execute('INSERT INTO rules(name,category,kind,config_json,tests_json,status,version,source_sample_id,reviewer,reason,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',args).lastrowid
     snapshot=dict(r,id=rid,version=version,action='REVIEW');c.execute('INSERT INTO rule_history(rule_id,version,snapshot_json,created_at) VALUES(?,?,?,?)',(rid,version,dumps(snapshot),now()));result={'id':rid,'version':version,'tests':tests}
    elif path=='/api/test':
     r,tests=validate_rule(dict(o['rule'],status='draft'));result={'tests':tests,'probe':evaluate(r,field(o,'text',20000))}
    else:raise ValueError('API không tồn tại')
   if path!='/api/test':
    try:
     with connect() as c:export_all(c)
    except OSError:result['warning']='Database đã lưu, nhưng xuất file lỗi. Kiểm tra quyền thư mục exports và bấm xuất lại.'
   self.reply(result)
  except (ValueError,TypeError,KeyError,sqlite3.IntegrityError) as e:self.reply({'error':str(e)},400)
  except Exception:
   import traceback;traceback.print_exc();self.reply({'error':'Lỗi máy chủ; dữ liệu chưa lưu hoặc cần kiểm tra log.'},500)

if __name__=='__main__':
 if os.environ.get('RENDER') and not PASSWORD:raise SystemExit('Set STUDIO_PASSWORD before deploying')
 init()
 with connect() as c:export_all(c)
 port=int(os.environ.get('PORT','8765'))
 print(f'Blacklist Studio: http://127.0.0.1:{port} — Ctrl+C để dừng',flush=True)
 HTTPServer((os.environ.get('HOST','0.0.0.0'),port),Handler).serve_forever()
