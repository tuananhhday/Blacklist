"""Admin-only staged Parquet uploads; decode selected columns in bounded batches."""
import itertools,json,re,secrets,tempfile,time,hashlib
from pathlib import Path

MAX_FILE_BYTES=256*1024*1024
CHUNK_BYTES=1024*1024
MAX_WINDOW_ROWS=5000
MAX_ROW_GROUP_BYTES=128*1024*1024
TTL_SECONDS=30*60

class UploadExpired(ValueError):pass
class UploadConflict(ValueError):pass

class ParquetUploads:
 def __init__(self):self.jobs={}
 def cleanup(self):
  for key,job in list(self.jobs.items()):
   if not job.get('import_running') and time.time()-job['touched']>TTL_SECONDS:self.remove(key)
 def remove(self,key):
  if self.jobs.get(key,{}).get('import_running'):raise UploadConflict('File đang nhập. Tạm dừng trước khi thay hoặc đóng file.')
  job=self.jobs.pop(key,None)
  if job:
   iterator=job.get('iterator')
   if iterator and hasattr(iterator,'close'):iterator.close()
   job['temp'].cleanup()
 def get(self,key,user_id):
  self.cleanup();job=self.jobs.get(key)
  if not job or job['user_id']!=user_id:raise UploadExpired('Phiên tải Parquet đã hết hoặc không thuộc tài khoản này. Chọn file và xem trước lại.')
  job['touched']=time.time();return job
 def start(self,user_id,o):
  name=o.get('name','');size=o.get('size')
  if not isinstance(name,str) or not name.lower().endswith(('.parquet','.pq')) or len(name)>255:raise ValueError('Chọn file .parquet hoặc .pq.')
  if type(size) is not int or not 12<=size<=MAX_FILE_BYTES:raise ValueError('File Parquet cần từ 12 byte đến 256 MiB.')
  self.cleanup()
  for key,job in list(self.jobs.items()):
   if job['user_id']==user_id:self.remove(key)
  if len(self.jobs)>=2:raise ValueError('Đang có hai file Parquet được xử lý. Thử lại sau.')
  tmp=tempfile.TemporaryDirectory(prefix='studio-parquet-');key=secrets.token_hex(16)
  self.jobs[key]={'temp':tmp,'path':Path(tmp.name)/'upload.parquet','name':name,'size':size,'written':0,'user_id':user_id,'touched':time.time(),'hasher':hashlib.sha256(),'metadata':None,'iterator':None,'cursor':None,'last':None}
  self.jobs[key]['path'].touch()
  return {'upload_id':key,'chunk_bytes':CHUNK_BYTES,'offset':0,'max_window_rows':MAX_WINDOW_ROWS}
 def append(self,key,user_id,offset,data):
  job=self.get(key,user_id)
  if type(offset) is not int or offset<0 or not data or len(data)>CHUNK_BYTES:raise ValueError('Khối tải lên không hợp lệ hoặc quá lớn.')
  if offset+len(data)>job['size']:raise ValueError('Dữ liệu tải lên vượt kích thước file đã khai báo.')
  if offset<job['written']:
   with job['path'].open('rb') as f:f.seek(offset);same=f.read(len(data))==data
   if offset+len(data)>job['written'] or not same:raise UploadConflict('Khối tải lại không khớp file. Tải lại từ đầu.')
  elif offset!=job['written']:raise UploadConflict('Sai vị trí tải file. Tải lại từ đầu.')
  else:
   with job['path'].open('ab') as f:f.write(data)
   job['written']+=len(data);job['hasher'].update(data)
  result={'offset':job['written'],'complete':job['written']==job['size']}
  if result['complete']:result['metadata']=self.metadata(job)
  return result
 def reader(self,job):
  if job['written']!=job['size']:raise ValueError('Chờ tải file hoàn tất trước khi đọc.')
  try:
   import pyarrow.parquet as pq
  except ImportError:raise ValueError('Server chưa cài PyArrow. Deploy lại với buildCommand cài requirements.txt.')
  try:return pq.ParquetFile(job['path'],memory_map=False,pre_buffer=False,thrift_string_size_limit=4*1024*1024,thrift_container_size_limit=100000)
  except Exception:raise ValueError('Không đọc được Parquet. File có thể bị hỏng, được mã hóa hoặc không đúng định dạng.')
 def metadata(self,job):
  if job['metadata']:return job['metadata']
  reader=self.reader(job)
  try:
   schema=reader.schema_arrow
   if len(schema.names)!=len(set(schema.names)):raise ValueError('File có tên cột trùng nhau. Đổi tên cột trước khi nhập.')
   if len(schema.names)>500:raise ValueError('File có quá nhiều cột; hãy xuất riêng các cột cần gán nhãn.')
   import pyarrow as pa
   def textual(kind):return pa.types.is_string(kind) or pa.types.is_large_string(kind) or pa.types.is_string_view(kind) or pa.types.is_dictionary(kind) and textual(kind.value_type)
   columns=[{'name':field.name,'type':str(field.type),'text_compatible':textual(field.type)} for field in schema]
   names={field['name'].casefold():field['name'] for field in columns if field['text_compatible']}
   suggestion=next((names[n] for n in ['text','comment','content','body','review','sentence','comment_text','review_text','noi_dung','bình_luận'] if n in names),None)
   if suggestion is None and len(names)==1:suggestion=next(iter(names.values()))
   job['metadata']={'name':job['name'],'rows':reader.metadata.num_rows,'sha256':job['hasher'].hexdigest(),'columns':columns,'suggested_text_column':suggestion}
   return job['metadata']
  finally:reader.close()
 def table(self,key,user_id,o):
  job=self.get(key,user_id);meta=self.metadata(job);offset=o.get('column_offset',0)
  if type(offset) is not int or offset<0 or offset>=max(1,len(meta['columns'])):raise ValueError('Trang cột không hợp lệ.')
  columns=meta['columns'][offset:offset+20];names=[c['name'] for c in columns];reader=self.reader(job);rows=[]
  try:
   for group in range(reader.num_row_groups):
    if not reader.metadata.row_group(group).num_rows:continue
    expanded=sum(reader.metadata.row_group(group).column(i).total_uncompressed_size for i in range(reader.metadata.row_group(group).num_columns) if reader.metadata.row_group(group).column(i).path_in_schema.split('.')[0] in names)
    if expanded>MAX_ROW_GROUP_BYTES:raise ValueError('Nhóm dữ liệu quá lớn để xem trên Render Free. Cần xuất file với row group nhỏ hơn.')
    for batch in reader.iter_batches(batch_size=8,row_groups=[group],columns=names,use_threads=False):
     for raw in batch.to_pylist():
      row={}
      for name in names:
       value=raw.get(name)
       if value is None:row[name]=''
       elif isinstance(value,str):row[name]=value[:240]+('…' if len(value)>240 else '')
       elif isinstance(value,(int,float,bool)):row[name]=str(value)
       else:row[name]='['+type(value).__name__+']'
      rows.append(row)
     break
    break
   return {'metadata':meta,'columns':columns,'rows':rows,'column_offset':offset,'column_page_size':20}
  finally:reader.close()
 def options(self,job,o):
  meta=self.metadata(job);columns={c['name'] for c in meta['columns']}
  mapping={'text':o.get('text_column') or meta['suggested_text_column']}
  if mapping['text'] not in columns:raise ValueError('Chọn cột chứa bình luận trong bảng xem trước.')
  if not next(c for c in meta['columns'] if c['name']==mapping['text'])['text_compatible']:raise ValueError('Cột đã chọn không phải văn bản. Bấm vào cột bình luận.')
  for key in ['context','source','synthetic']:
   col=o.get(key+'_column')
   if col and col not in columns:raise ValueError('Không có cột '+str(col)+' trong Parquet.')
   mapping[key]=col or None
  synthetic=o.get('synthetic',False)
  if type(synthetic) is not bool:raise ValueError('Loại dữ liệu mô phỏng không hợp lệ.')
  if o.get('all_rows') is True or not any(k in o for k in ['start','count']):
   return {'mapping':mapping,'synthetic':synthetic,'start':0,'end':meta['rows']}
  start=o.get('start',0);count=o.get('count',MAX_WINDOW_ROWS)
  if type(start) is not int or type(count) is not int or start<0 or not 1<=count<=MAX_WINDOW_ROWS or start>=meta['rows']:raise ValueError('Dòng bắt đầu tính từ 0; mỗi đợt cần 1–5.000 dòng và nằm trong file.')
  return {'mapping':mapping,'synthetic':synthetic,'start':start,'end':min(start+count,meta['rows'])}
 def rows(self,job,options):
  mapping=options['mapping'];selected=list(dict.fromkeys(c for c in mapping.values() if c));reader=self.reader(job);global_start=0
  try:
   for group in range(reader.num_row_groups):
    group_meta=reader.metadata.row_group(group);end=global_start+group_meta.num_rows
    if end<=options['start']:global_start=end;continue
    if global_start>=options['end']:return
    expanded=sum(group_meta.column(i).total_uncompressed_size for i in range(group_meta.num_columns) if group_meta.column(i).path_in_schema.split('.')[0] in selected)
    if expanded>MAX_ROW_GROUP_BYTES:raise ValueError('Nhóm dòng của cột đã chọn vượt 128 MiB giải nén. Hãy chia file thành row group nhỏ hơn để chạy trên Render Free.')
    index=global_start
    for batch in reader.iter_batches(batch_size=64,row_groups=[group],columns=selected,use_threads=False):
     for raw in batch.to_pylist():
      current=index;index+=1
      if current<options['start']:continue
      if current>=options['end']:return
      text=raw.get(mapping['text'])
      if text is None or isinstance(text,str) and not text.strip():yield {'skip':'empty','row':current};continue
      if not isinstance(text,str):raise ValueError(f'Dòng {current}: cột bình luận không phải chuỗi. Chọn cột văn bản khác.')
      if len(text)>20000:yield {'skip':'too_long','row':current};continue
      context=raw.get(mapping['context']) if mapping['context'] else ''
      source=raw.get(mapping['source']) if mapping['source'] else job['name']
      context='' if context is None else context;source=job['name'] if source is None or source=='' else source
      if not isinstance(context,str) or len(context)>20000 or not isinstance(source,str) or len(source)>500:raise ValueError(f'Dòng {current}: context/source phải là chuỗi với độ dài hợp lệ.')
      synthetic=raw.get(mapping['synthetic']) if mapping['synthetic'] else options['synthetic']
      if isinstance(synthetic,str) and synthetic.lower() in ['true','false']:synthetic=synthetic.lower()=='true'
      if type(synthetic) is not bool:raise ValueError(f'Dòng {current}: synthetic cần true/false.')
      yield {'sample':{'text':text,'context':context,'source':source,'synthetic':synthetic},'row':current}
    global_start=end
  finally:reader.close()
 def preview(self,key,user_id,o):
  job=self.get(key,user_id);options=self.options(job,o)
  iterator=self.rows(job,options)
  try:items=list(itertools.islice(iterator,5))
  finally:iterator.close()
  old=job.get('iterator')
  if old:old.close()
  job.update(options=options,iterator=None,cursor=options['start'],last=None)
  return {'metadata':self.metadata(job),'options':options,'preview':items,'row_count':options['end']-options['start']}
 def batch(self,key,user_id,o):
  job=self.get(key,user_id);offset=o.get('offset');limit=o.get('limit',50)
  if not job.get('options'):raise ValueError('Xem trước và chọn cột trước khi nhập.')
  if type(offset) is not int or type(limit) is not int or not 1<=limit<=50:raise ValueError('Mỗi lô tối đa 50 dòng.')
  last=job.get('last')
  if last and last['offset']==offset and last['limit']==limit:return last['response']
  if offset!=job['cursor']:raise UploadConflict('Vị trí nhập đã thay đổi. Xem trước lại để bắt đầu đợt mới.')
  if job['iterator'] is None:job['iterator']=self.rows(job,job['options'])
  items=list(itertools.islice(job['iterator'],limit));processed=len(items)
  job['cursor']+=processed
  result={'rows':[r['sample'] for r in items if 'sample' in r],'processed':processed,'next_offset':job['cursor'],'end':job['options']['end'],'skipped_empty':sum(r.get('skip')=='empty' for r in items),'skipped_too_long':sum(r.get('skip')=='too_long' for r in items),'done':job['cursor']>=job['options']['end']}
  if not processed and not result['done']:raise ValueError('Không đọc đủ dữ liệu Parquet. File có thể bị lỗi.')
  job['last']={'offset':offset,'limit':limit,'response':result}
  return result
 def action(self,path,user_id,o):
  if path.endswith('/start'):return self.start(user_id,o)
  key=o.get('upload_id')
  if path.endswith('/table'):return self.table(key,user_id,o)
  if path.endswith('/preview'):return self.preview(key,user_id,o)
  if path.endswith('/rows'):return self.batch(key,user_id,o)
  if path.endswith('/close'):self.get(key,user_id);self.remove(key);return {'closed':True}
  raise ValueError('Thao tác Parquet không tồn tại.')
