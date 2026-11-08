// Interaction checks against actual HTML IDs and the curation controller.
// This is a DOM logic harness, not a visual/browser test.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(__dirname+'/static/index.html','utf8');
function storage(){const values=new Map();return {getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,String(value)),removeItem:key=>values.delete(key),key:index=>[...values.keys()][index],get length(){return values.size}}}
class Element{
 constructor(tag='div',text=''){this.tagName=tag.toUpperCase();this._text=text;this.children=[];this.parentElement=null;this.listeners={};this.dataset={};this.className='';this.value='';this.checked=false;this.disabled=false;this.hidden=false;this.open=false;this.style={};this.files=[];this.classList={contains:name=>this.className.split(/\s+/).includes(name),toggle:(name,on)=>{const set=new Set(this.className.split(/\s+/).filter(Boolean));const next=on===undefined?!set.has(name):on;next?set.add(name):set.delete(name);this.className=[...set].join(' ');return next},add:name=>this.classList.toggle(name,true),remove:name=>this.classList.toggle(name,false)}}
 get textContent(){return this._text+this.children.map(child=>child.textContent).join('')}
 set textContent(value){this._text=String(value??'');this.children=[]}
 set innerHTML(_){throw Error('User content must not be rendered with innerHTML')}
 append(...children){for(let child of children){if(typeof child!=='object')child=new Element('#text',String(child));child.parentElement=this;this.children.push(child)}}
 replaceChildren(...children){this._text='';this.children=[];this.append(...children)}
 setAttribute(name,value){this[name]=String(value);if(name==='class')this.className=String(value)}
 addEventListener(name,listener){(this.listeners[name]??=[]).push(listener)}
 querySelectorAll(selector){const selectors=selector.split(',').map(v=>v.trim());const found=[];const matches=e=>selectors.some(s=>s[0]==='.'?e.classList.contains(s.slice(1)):s.startsWith('[data-')?Object.hasOwn(e.dataset,s.slice(6,-1).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())):e.tagName===s.toUpperCase());const walk=e=>{for(const child of e.children){if(matches(child))found.push(child);walk(child)}};walk(this);return found}
 closest(selector){let e=this;while(e){if(selector[0]==='.'&&e.classList.contains(selector.slice(1)))return e;e=e.parentElement}return null}
 contains(target){return this===target||this.children.some(child=>child.contains(target))}
 reset(){for(const control of this.querySelectorAll('input,select,textarea')){control.value=control.defaultValue??'';control.checked=!!control.defaultChecked}}
 showModal(){this.open=true}close(){this.open=false}focus(){}scrollIntoView(){}click(){return emit(this,'click')}
}
const ids={},root=new Element('document'),stack=[root],voidTags=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
for(const token of html.match(/<!--[\s\S]*?-->|<![^>]*>|<[^>]+>|[^<]+/g)||[]){
 if(token.startsWith('<!'))continue;
 if(token.startsWith('</')){const closing=token.match(/^<\/([\w-]+)/)?.[1]?.toUpperCase();assert.equal(stack.at(-1).tagName,closing,'Malformed HTML closing '+closing);stack.pop();continue}
 if(token.startsWith('<')){const match=token.match(/^<([\w-]+)/);if(!match)continue;const tag=match[1].toLowerCase(),element=new Element(tag);const attrs={};for(const a of token.matchAll(/([\w:-]+)(?:\s*=\s*"([^"]*)"|\s*=\s*'([^']*)')?/g)){if(a.index===1)continue;attrs[a[1]]=a[2]??a[3]??''}for(const[name,value]of Object.entries(attrs)){if(name==='id'){element.id=value;assert.ok(!ids[value],'duplicate id '+value);ids[value]=element}else if(name==='class')element.className=value;else if(name.startsWith('data-'))element.dataset[name.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=value;else if(name==='value')element.value=value;else if(['checked','hidden','disabled'].includes(name))element[name]=true;else element[name]=value}stack.at(-1).append(element);if(!voidTags.has(tag)&&!token.endsWith('/>'))stack.push(element);
 }else if(stack.at(-1).tagName==='OPTION')stack.at(-1)._text+=token;
}
assert.equal(stack.length,1,'HTML contains unclosed elements');
// All controllers share this page: preserve import/export, backup and account
// controls when replacing the Blacklist editor or its dialog.
for(const file of ['app.js','admin.js','parquet.js','studio.js'])for(const ref of fs.readFileSync(__dirname+'/static/'+file,'utf8').matchAll(/(?:\$|el)\('([^']+)'\)/g))assert.ok(ids[ref[1]],file+' refers to missing control '+ref[1]);
for(const element of Object.values(ids)){if(element.tagName==='SELECT')element.value=element.children.find(child=>child.tagName==='OPTION')?.value||'';element.defaultValue=element.value;element.defaultChecked=element.checked}
const events={},timers=new Map();let timerSequence=0;
const get=id=>{assert.ok(ids[id],'Missing HTML ID '+id);return ids[id]};
const document={getElementById:get,createElement:tag=>new Element(tag),createTextNode:text=>new Element('#text',text),querySelectorAll:selector=>root.querySelectorAll(selector),body:root.querySelectorAll('body')[0],addEventListener:(name,fn)=>(events[name]??=[]).push(fn)};
const currentState={database_id:'test-db',categories:{co_bac:'Cờ bạc',spam:'Spam'}};
const calls=[],notices=[];let apiHandler;
const context={console,assert,document,localStorage:storage(),URL,URLSearchParams,Blob,Date,Promise,setTimeout:fn=>{timers.set(++timerSequence,fn);return timerSequence},clearTimeout:id=>timers.delete(id),currentUser:{id:1,role:'admin',display_name:'Admin'},state:currentState,clientId:'a'.repeat(32),confirm:()=>true,node:(tag,text,cls)=>{const e=new Element(tag,text===undefined?'':String(text));e.className=cls||'';return e},notice:(...args)=>notices.push(args),backupUI:()=>{},api:async(path,body)=>{calls.push({path,body:body===undefined?undefined:JSON.parse(JSON.stringify(body))});return apiHandler(path,body)},window:{addEventListener:(name,fn)=>(events[name]??=[]).push(fn),getSelection:()=>null},tab:name=>{document.body.dataset.view=name;get('studio').hidden=name!=='studio';get('demo').hidden=name!=='demo'}};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/static/studio.js','utf8'),context);
async function emit(element,event,extra={}){const eventObject={preventDefault(){},target:element,...extra};for(const listener of element.listeners[event]||[])await listener(eventObject);if(event==='click'&&element.onclick)await element.onclick(eventObject)}
const ui=context.window.studioUi;
let serverDraft=null,liveItem=null,sourceRows=[];
function defaultApi(path,body){
 if(path.startsWith('/api/studio/draft?'))return {draft:serverDraft?{payload:serverDraft}:null};
 if(path==='/api/studio/draft')return {draft_saved:true,changed:true,backup:{configured:false,version:3}};
 if(path==='/api/studio/draft/delete')return {deleted:true};
 if(path.startsWith('/api/studio/items?'))return {items:liveItem?[{...liveItem,examples:undefined,example_count:liveItem.examples.length}]:[],total:liveItem?1:0,page_size:30,counts:{draft:0,published:liveItem?1:0,live:7}};
 if(path.startsWith('/api/studio/sources?'))return {sources:sourceRows,total:sourceRows.length,page_size:30};
 if(path.startsWith('/api/studio/item?id='))return {item:liveItem};
 if(path==='/api/studio/preview')return {preview:true,item:body.item,tests:body.item.examples.map(example=>({...example,actual:example.expected,passed:true})),result:{decision:body.item.mode==='block'?'BLOCK':'REVIEW',matches:[],checked_count:1}};
 if(path==='/api/studio/item'){liveItem={...body,id:body.id||42,version:(body.version||0)+1,created_by_user_id:1,published_version:body.status==='published'?(body.version||0)+1:null,examples:body.examples.map((ex,index)=>({...ex,id:ex.id||100+index}))};return {item:liveItem,tests:body.examples.map(ex=>({...ex,actual:ex.expected,passed:true})),backup:{configured:false,version:4}}}
 if(path==='/api/studio/demo')return {decision:'BLOCK',explanation:'Đã khớp điều kiện.',matches:[{name:'Mời gọi',category:'co_bac',evidence:[{start:2,end:10,text:'Vào nhóm'}],reasons:['Đủ dấu hiệu']}],checked_count:1,published_count:1,scope_note:'Chưa chạy fastText.'};
 throw Error('Unexpected API '+path);
}
apiHandler=defaultApi;
(async()=>{
 await ui.load('studio');await emit(get('studioFillTemplate'),'click');
 let snapshot=ui.getDraft();assert.equal(snapshot.item.examples[0].context,'');assert.equal(snapshot.item.examples[0].expected,'MATCH');assert.equal(snapshot.item.config.topics.length,2);
 await ui.flushDraft();const cloudWrite=calls.find(call=>call.path==='/api/studio/draft');assert.ok(cloudWrite);assert.equal(cloudWrite.body.key,'db-test-db:new');assert.equal(cloudWrite.body.payload.dirty,true);
 await emit(get('studioCheck'),'click');assert.ok(get('studioTests').textContent.includes('3 / 3'));assert.ok(get('studioTests').textContent.includes('Bạn muốn: Chặn'));assert.ok(get('studioTests').textContent.includes('Hệ thống khi bật chặn: Chặn'));assert.ok(!get('studioTests').textContent.includes('MATCH'));
 // A plain answer changes manual example semantics without asking for a second role.
 const manualCard=get('studioExamples').children[2],manualAnswer=manualCard.querySelectorAll('select')[0];manualAnswer.value='MATCH';await manualAnswer.onchange();assert.equal(ui.getDraft().item.examples[2].role,'violation');manualAnswer.value='NO_MATCH';await manualAnswer.onchange();assert.equal(ui.getDraft().item.examples[2].role,'counterexample');
 const manualText=manualCard.querySelectorAll('textarea')[0];manualText.value='Hôm nay chúng mình cùng ôn bài và đọc sách nhé.';await emit(manualText,'input');assert.equal(ui.getDraft().item.examples[2].text,manualText.value);
 get('studioMode').value='block';await emit(get('studioPublish'),'click');assert.equal(liveItem.status,'published');assert.equal(liveItem.mode,'block');
 // Server example IDs must be sent back so source snapshots can remain immutable.
 await emit(get('studioCheck'),'click');let lastPreview=calls.filter(call=>call.path==='/api/studio/preview').at(-1);assert.equal(lastPreview.body.item.examples[0].id,100);
 assert.ok(get('studioItems').textContent.includes('3 ví dụ'));
 await ui.load('demo');assert.equal(get('demoBankState').textContent,'7 mục đang dùng');
 get('demoText').value='😀 Vào nhóm cá cược';await emit(get('demoForm'),'submit');assert.equal(get('demoHeadline').textContent,'Đề xuất chặn');assert.equal(get('demoAnnotatedText').querySelectorAll('mark')[0].textContent,'Vào nhóm');assert.ok(get('demoScopeNote').textContent.includes('fastText'));
 // Explicit source answers are retained, and switching group cannot keep a Chặn answer for a negative source label.
 const sourceRow={id:81,text:'Vào nhóm cá cược mới.',context:'',review:{id:91,decision:'VIOLATION',labels:{co_bac:1,spam:0}}};
 apiHandler=(path,body)=>path.startsWith('/api/sample?id=')?sourceRow:defaultApi(path,body);
 await ui.openSource(81,91);get('studioSourceExpected').value='MATCH';await emit(get('studioSourceExpected'),'change');assert.equal(ui.getDraft().source._example_expected,'MATCH');
 get('studioCategory').value='spam';await emit(get('studioCategory'),'change');assert.equal(ui.getDraft().source._example_expected,undefined);assert.notEqual(get('studioSourceExpected').value,'MATCH');assert.equal(get('studioSourceExpected').children.find(option=>option.value==='MATCH').disabled,true);
 get('studioCategory').value='co_bac';await emit(get('studioCategory'),'change');await emit(get('studioItemForm'),'submit');
 const sourceExample=ui.getDraft().item.examples.find(ex=>ex.source_sample_id===81);assert.ok(sourceExample);const sourceExampleId=sourceExample.id;
 get('studioSourceExpected').value='REVIEW';await emit(get('studioSourceExpected'),'change');assert.equal(ui.getDraft().item.examples.find(ex=>ex.id===sourceExampleId).expected,'REVIEW');assert.equal(ui.getDraft().item.examples.find(ex=>ex.id===sourceExampleId).role,'violation');
 // Generate editable examples from current words and keep every existing saved example ID.
 get('studioTopicInput').value='sòng bạc';await emit(get('studioAddTopic'),'click');const oldIds=ui.getDraft().item.examples.map(ex=>ex.id).filter(Boolean);await emit(get('studioGenerateExamples'),'click');for(const id of oldIds)assert.ok(ui.getDraft().item.examples.some(ex=>ex.id===id));assert.ok(get('studioEditorStatus').textContent.includes('Đã thêm'));
 apiHandler=defaultApi;
 // Closing a session clears source/demo content and invalidates late responses.
 let finishOldDemo;apiHandler=(path,body)=>path==='/api/studio/demo'?new Promise(resolve=>{finishOldDemo=resolve}):defaultApi(path,body);
 const pending=emit(get('demoForm'),'submit');assert.equal(get('demoRun').disabled,true);ui.reset();context.currentUser={id:2,role:'member',display_name:'Member'};await ui.load('demo');finishOldDemo({decision:'BLOCK',explanation:'PRIVATE OLD RESPONSE',matches:[],checked_count:1});await pending;assert.equal(get('demoResult').hidden,true);assert.equal(get('demoRun').disabled,false);assert.ok(!get('demoExplanation').textContent.includes('PRIVATE'));
 // An older cloud draft must not overwrite the latest fetched item version.
 context.currentUser={id:1,role:'admin',display_name:'Admin'};ui.reset();apiHandler=defaultApi;liveItem={...liveItem,status:'draft',version:6,config:{topics:['phiên bản mới'],actions:['tham gia'],pattern:''}};serverDraft={dirty:true,updated_at:Date.now()+100000,item:{...liveItem,version:5,config:{topics:['OLD DRAFT'],actions:['mời gọi'],pattern:''}}};await ui.load('studio');await get('studioItems').children[0].onclick();await new Promise(resolve=>setImmediate(resolve));assert.equal(ui.getDraft().item.config.topics[0],'phiên bản mới');
 // Same-version newer cloud data can be restored without validating a partial rule.
 serverDraft={...serverDraft,item:{...liveItem,config:{topics:['Bản nháp máy chủ'],actions:[],pattern:''}}};await get('studioItems').children[0].onclick();await new Promise(resolve=>setImmediate(resolve));assert.equal(ui.getDraft().item.config.topics[0],'Bản nháp máy chủ');assert.equal(ui.getDraft().item.config.actions.length,0);await ui.flushDraft();assert.equal(calls.filter(call=>call.path==='/api/studio/draft').at(-1).body.payload.item.id,42);
 // Import uses the new versioned format and never treats a source pack as live.
 serverDraft=null;apiHandler=(path,body)=>path==='/api/studio/import'?{added:1,duplicates:0}:defaultApi(path,body);get('studioImportPack').files=[{size:100,text:async()=>JSON.stringify({schema_version:2,items:[liveItem]})}];await emit(get('studioImportPack'),'change');assert.equal(calls.filter(call=>call.path==='/api/studio/import').at(-1).body.pack.schema_version,2);
 // Late source/item list results cannot populate another user's workspace.
 let resolveOldList;apiHandler=(path,body)=>path.startsWith('/api/studio/items?')?new Promise(resolve=>{resolveOldList=resolve}):defaultApi(path,body);const oldLoad=ui.load('studio');await Promise.resolve();ui.reset();context.currentUser={id:3,role:'member',display_name:'Other'};apiHandler=defaultApi;await ui.load('studio');resolveOldList({items:[{id:999,name:'PRIVATE OLD ITEM',status:'draft',category:'co_bac',example_count:1}],total:1});await oldLoad;assert.ok(!get('studioItems').textContent.includes('PRIVATE OLD ITEM'));
 console.log('PASS: source/definition curation controller, valid demo template, cloud/local revision recovery, immutable example IDs, pinned-scope counts, Unicode evidence, account isolation and pack-v2 import.');
})().catch(error=>{console.error(error);process.exitCode=1});
