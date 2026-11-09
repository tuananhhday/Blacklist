// Interaction checks against actual HTML IDs and the curation controller.
// This is a DOM logic harness, not a visual/browser test.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(__dirname+'/static/sandbox/index.html','utf8');
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
 querySelector(selector){return this.querySelectorAll(selector)[0]||null}
 remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(c=>c!==this)}
 closest(selector){let e=this;while(e){if(selector[0]==='.'&&e.classList.contains(selector.slice(1)))return e;e=e.parentElement}return null}
 contains(target){return this===target||this.children.some(child=>child.contains(target))}
 reset(){for(const control of this.querySelectorAll('input,select,textarea')){control.value=control.defaultValue??'';control.checked=!!control.defaultChecked}}
 showModal(){this.open=true}close(){this.open=false}focus(){}scrollIntoView(){}click(){return emit(this,'click')}
}
const ids={},root=new Element('document'),stack=[root],voidTags=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
for(const token of html.match(/<!--[\s\S]*?-->|<![^>]*>|<[^>]+>|[^<]+/g)||[]){
 if(token.startsWith('<!'))continue;
 if(token.startsWith('</')){if(stack.length>1)stack.pop();continue}
 if(token.startsWith('<')){const match=token.match(/^<([\w-]+)/);if(!match)continue;const tag=match[1].toLowerCase(),element=new Element(tag);const attrs={};for(const a of token.matchAll(/([\w:-]+)(?:\s*=\s*"([^"]*)"|\s*=\s*'([^']*)')?/g)){if(a.index===1)continue;attrs[a[1]]=a[2]??a[3]??''}for(const[name,value]of Object.entries(attrs)){if(name==='id'){element.id=value;assert.ok(!ids[value],'duplicate id '+value);ids[value]=element}else if(name==='class')element.className=value;else if(name.startsWith('data-'))element.dataset[name.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=value;else if(name==='value')element.value=value;else if(['checked','hidden','disabled'].includes(name))element[name]=true;else element[name]=value}stack.at(-1).append(element);if(!voidTags.has(tag)&&!token.endsWith('/>'))stack.push(element);
 }else if(stack.at(-1).tagName==='OPTION')stack.at(-1)._text+=token;
}
for(const element of Object.values(ids)){if(element.tagName==='SELECT')element.value=element.children.find(child=>child.tagName==='OPTION')?.value||'';element.defaultValue=element.value;element.defaultChecked=element.checked}
const events={},timers=new Map();let timerSequence=0;
const get=id=>{assert.ok(ids[id],'Missing HTML ID '+id);return ids[id]};
const document={getElementById:get,createElement:tag=>new Element(tag),createTextNode:text=>new Element('#text',text),querySelectorAll:selector=>root.querySelectorAll(selector),body:root.querySelectorAll('body')[0],addEventListener:(name,fn)=>(events[name]??=[]).push(fn)};
const memory=storage(),notices=[],browserEvents={};
const context={console,document,localStorage:memory,URL,URLSearchParams,Blob,Date,Promise,performance,setTimeout:fn=>{timers.set(++timerSequence,fn);return timerSequence},clearTimeout:id=>timers.delete(id),confirm:()=>true,location:{hash:'#bank'},history:{replaceState(){}},window:{addEventListener:(name,fn)=>(browserEvents[name]??=[]).push(fn)}};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/static/sandbox/phrase_marker.js','utf8'),context);vm.runInContext(fs.readFileSync(__dirname+'/static/sandbox/engine.js','utf8'),context);vm.runInContext(fs.readFileSync(__dirname+'/static/sandbox/app.js','utf8'),context);
async function emit(element,event,extra={}){const e={preventDefault(){},target:element,...extra};for(const listener of element.listeners[event]||[])await listener(e);if(element['on'+event])await element['on'+event](e)}
(async()=>{
 await emit(get('newItem'),'click');await emit(get('fillStarter'),'click');
 assert.equal(get('itemTopics').value,'cá cược\ncá độ');assert.equal(get('exampleRows').children.length,3);assert.equal(get('exampleRows').children[0].querySelector('select').value,'MATCH');
 await emit(get('checkExamples'),'click');assert.match(get('exampleTestResults').textContent,/hiểu đúng ý bạn/);assert.ok(!get('exampleTestResults').textContent.includes('MATCH'));
 get('itemMode').value='block';await emit(get('itemForm'),'change');assert.equal(get('exampleTestResults').hidden,true);await emit(get('publishItem'),'click');
 let pack=JSON.parse(memory.getItem('blacklist_sandbox_v2')),added=pack.items.find(i=>i.id===3);assert.equal(added.status,'published');assert.equal(added.mode,'block');assert.equal(pack.published_items.find(i=>i.id===3).examples.length,3);
 await emit(get('navDemo'),'click');await emit(get('quickSamples').children[0],'click');assert.match(get('resultContent').textContent,/Blacklist đề xuất chặn/);assert.ok(!get('resultContent').textContent.includes('BLOCK'));
 await emit(get('quickSamples').children[1],'click');assert.match(get('resultContent').textContent,/Câu này cần được xem thêm/);assert.ok(!get('resultContent').textContent.includes('REVIEW'));
 await emit(get('quickSamples').children[4],'click');assert.match(get('resultContent').textContent,/Cho đi tiếp qua Blacklist/);assert.ok(!get('resultContent').textContent.includes('NO_MATCH'));
 await emit(get('navBank'),'click');const select=get('exampleRows').children[0].querySelector('select');select.value='NO_MATCH';await emit(select,'change');await emit(get('itemForm'),'change');await emit(get('itemForm'),'submit');
 pack=JSON.parse(memory.getItem('blacklist_sandbox_v2'));added=pack.items.find(i=>i.id===3);assert.equal(added.examples[0].expected,'NO_MATCH');assert.equal(added.examples[0].role,'counterexample');assert.equal(pack.published_items.find(i=>i.id===3).examples[0].expected,'MATCH','Saving changed answers as draft must preserve live version');
 console.log('PASS: sandbox DOM template → examples → activate → demo, plain outcomes, editable answers, and live-version preservation.');
})().catch(e=>{console.error(e);process.exitCode=1});
