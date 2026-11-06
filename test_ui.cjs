// DOM-level logic checks without browser dependencies or production data.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
function storage(){const data=new Map();return {getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,String(v)),removeItem:k=>data.delete(k),key:i=>[...data.keys()][i],get length(){return data.size}}}
class Element{constructor(){this.value='';this.checked=false;this.textContent='';this.children=[];this.listeners={};this.dataset={};this.hidden=false;this.classList={toggle(){},add(){},remove(){}}}append(...items){this.children.push(...items)}replaceChildren(...items){this.children=items}setAttribute(k,v){this[k]=v}addEventListener(k,fn){(this.listeners[k]??=[]).push(fn)}animate(){this.animated=(this.animated||0)+1}closest(){return this}}
const elements={},labelSelects=[],motion={matches:false};
const context={console,assert,crypto:require('node:crypto').webcrypto,sessionStorage:storage(),localStorage:storage(),matchMedia:()=>motion,motion,labelSelects,elements,Element,AbortController,URL,Blob,fetch:()=>new Promise(()=>{}),setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,window:{addEventListener(){},getSelection(){}},document:{getElementById:id=>elements[id]??=new Element(),body:new Element(),querySelectorAll:q=>q==='[data-label]'?labelSelects:[],querySelector:q=>{const m=q.match(/data-label="(.*?)"/);return m?labelSelects.find(e=>e.dataset.label===m[1]):null},createElement:()=>new Element(),addEventListener(){}},confirm:()=>true};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/static/app.js','utf8'),context);
vm.runInContext(`(async()=>{
 const csv='comment,context,source,synthetic\\n"Có dấu phẩy, và \\"trích dẫn\\"",bối cảnh,dataset,false\\n';
 const parsed=parseCsv('text,source\\n"Câu có dấu phẩy, vẫn một ô",test\\n');assert.equal(parsed[0].text,'Câu có dấu phẩy, vẫn một ô');
 elements.textColumn.value='comment';previewFiles=[{name:'a.csv',size:100,text:async()=> 'comment,source,synthetic\\n"Xin chào, bạn",dataset,false\\n'}];await previewSamples();assert.equal(previewRows[0].text,'Xin chào, bạn');assert.equal(previewRows[0].synthetic,false);
 elements.textColumn.value='';previewFiles=[{name:'b.txt',size:100,text:async()=> 'Câu thứ nhất\\nCâu thứ hai\\n'}];await previewSamples();assert.equal(previewRows.length,2);assert.equal(previewRows[1].source,'b.txt');
 previewFiles=[{name:'c.json',size:100,text:async()=> JSON.stringify({comments:[{body:'Nội dung thực',synthetic:false}]})}];await previewSamples();assert.equal(previewRows[0].text,'Nội dung thực');
 state={database_id:'db1',samples:[{id:1,fingerprint:'fp'}],categories:{a:'Nhóm A',b:'Nhóm B'}};selected=1;selectedRevision=2;
 for(const code of ['a','b']){const e=new Element();e.dataset.label=code;e.value='';labelSelects.push(e)}
 for(const id of ['decision','intent','reason','evidence','reviewSummary','saveState'])$(id);elements.decision.value='';elements.intent.value='';elements.reason.value='Ghi chú đang gõ';elements.evidence.value='';
 setLabel('a','1',new Element());assert.equal(readLabels().a,1);assert.equal(readLabels().b,null);const stored=JSON.parse(localStorage.getItem(draftKey()));assert.equal(stored.base_revision,2);assert.equal(stored.reason,'Ghi chú đang gõ');assert.equal(stored.fingerprint,'fp');
 await elements.undoLabels.listeners.click[0]({});assert.equal(readLabels().a,null);
 quiet=true;const el=new Element();animate(el,[{},{}]);assert.equal(el.animated,undefined);quiet=false;motion.matches=true;animate(el,[{},{}]);assert.equal(el.animated,undefined);
 const calls=[];fetch=async(path,options)=>{calls.push([path,options]);if(calls.length===1)return {ok:false,json:async()=>({error:'Phiên hết hạn. Tải lại trang.'})};if(path==='/api/session')return {ok:true,json:async()=>({token:'new-token'})};return {ok:true,json:async()=>({saved:true})}};
 await api('/api/review',{sample_id:1,operation_id:'a'.repeat(32)});const writes=calls.filter(c=>c[0]==='/api/review');assert.equal(writes.length,2);assert.equal(writes[0][1].body,writes[1][1].body);assert.equal(writes[1][1].headers['X-Studio-Token'],'new-token');
 console.log('PASS: CSV/JSON/TXT mapping, null labels, undo, durable local draft, quiet/reduced-motion, session recovery and stable retry operation.');
})()`,context).catch(e=>{console.error(e);process.exitCode=1});
