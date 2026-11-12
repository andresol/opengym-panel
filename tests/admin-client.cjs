// Isolated DOM/client behaviour. A real browser render is verified separately.
const {parseHTML}=require(process.env.LINKEDOM_MODULE||'linkedom');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
 const header=fs.readFileSync(path.join(__dirname,'../firmware/custom_components/gym_native/admin_page.h'),'utf8');
 const html=process.env.ADMIN_HTML_PATH ? fs.readFileSync(process.env.ADMIN_HTML_PATH,'utf8') : header.split('R"HTML(')[1].split(')HTML";')[0];
 const english=process.env.PANEL_TEST_LANGUAGE==='en';
 const text=(nb,en)=>english?en:nb;
 const {window,document}=parseHTML(html);const $=id=>document.getElementById(id);
 // Linkedom's select has a getter only, unlike a browser HTMLSelectElement.
 Object.defineProperty($('wake'),'value',{value:'5',writable:true});
 const state={version:'1.1.14',uptimeSeconds:7200,wifiConnected:true,clockValid:true,localTime:'21.10.2026 23:10:00',displayOn:false,brightness:20,nightEnabled:true,nightStart:1380,nightEnd:420,dayBrightness:100,nightBrightness:20,wakeMinutes:5,settingsStored:false,storeSequence:0,routes:{nightStart:'Natt start',nightEnd:'Natt slutt',dayBrightness:'Lys dag',nightBrightness:'Lys natt',wakeMinutes:'Vekketid',nightEnabled:'Nattmodus',save:'Lagre skjerminnstillinger',light:'Skjermlys'}};
 const calls=[],intervals=[];let fail=false;
 const ctx={document,window:{location:{host:'panel.test'}},console,String,Number,Math,Object,Error,encodeURIComponent,Promise,setTimeout:fn=>queueMicrotask(fn),setInterval:fn=>intervals.push(fn),fetch:async(raw,options)=>{
  const url=new URL(raw,'http://panel.test');const method=options.method;calls.push({path:url.pathname,method,query:url.search});
  if(fail&&method==='POST')return {ok:false,status:503};
  if(url.pathname==='/admin/status')return {ok:true,status:200,json:async()=>structuredClone(state)};
  if(method==='POST'){
   if(url.pathname.startsWith('/number/')){const id=decodeURIComponent(url.pathname.split('/')[2]),key=Object.keys(state.routes).find(k=>state.routes[k]===id);assert(key);state[key]=Number(url.searchParams.get('value'));}
   else if(url.pathname.startsWith('/button/')){assert.equal(decodeURIComponent(url.pathname.split('/')[2]),state.routes.save);state.storeSequence++;state.settingsStored=true;}
   else if(url.pathname.startsWith('/light/')){assert.equal(decodeURIComponent(url.pathname.split('/')[2]),state.routes.light);state.displayOn=url.pathname.endsWith('turn_on');}
   else if(url.pathname.startsWith('/switch/')){assert.equal(decodeURIComponent(url.pathname.split('/')[2]),state.routes.nightEnabled);state.nightEnabled=url.pathname.endsWith('turn_on');}
   else assert.fail('Unexpected write route');
   return {ok:true,status:200};
  }
  assert.fail('Unexpected read route');
 }};
 vm.createContext(ctx);vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],ctx);
 const settle=async()=>{for(let i=0;i<100;i++)await Promise.resolve();};
 const fire=(id,type)=>$(id).dispatchEvent(new window.Event(type,{bubbles:true,cancelable:true}));
 await settle();assert.equal($('display').textContent,text('Av','Off'));assert.equal($('version').textContent,'1.1.14');assert.equal($('start').value,'23:00');assert.equal($('end').value,'07:00');assert.equal(calls.filter(c=>c.method==='POST').length,0);
 $('day').value='70';fire('day','input');state.dayBrightness=90;intervals[0]();await settle();assert.equal($('day').value,'70','Polling must not erase an edit');
 fire('settings','submit');await settle();assert.equal(state.dayBrightness,70);assert.equal(state.storeSequence,1);assert.equal($('result').textContent,text('Innstillingene er lagret.','Settings saved.'));assert(calls.some(c=>c.path==='/button/Lagre%20skjerminnstillinger/press'));
 assert(calls.some(c=>c.path==='/number/Lys%20dag/set'));
 state.routes.light='Skjermlys · test';intervals[0]();await settle();
 fire('on','click');await settle();assert(calls.some(c=>c.path==='/light/Skjermlys%20%C2%B7%20test/turn_on'));assert.equal(state.displayOn,true);assert.equal($('display').textContent,text('På · 20 %','On · 20 %'));
 fire('off','click');await settle();assert.equal(state.displayOn,false);
 const writes=calls.filter(c=>c.method==='POST').length;
 $('start').value='07:00';fire('start','input');fire('settings','submit');await settle();assert.equal(calls.filter(c=>c.method==='POST').length,writes);assert($('result').textContent.includes(text('forskjellig start','different start')));
 $('start').value='23:00';$('day').value='60';fire('day','input');fail=true;fire('settings','submit');await settle();assert($('result').classList.contains('error'));assert(!$('result').textContent.includes(text('er lagret','Settings saved')));assert.equal(state.dayBrightness,70);
 assert.equal(document.querySelector('a[download]').getAttribute('href'),'/admin/diagnostics.json');
 assert(!/https?:\/\//.test(html),'Admin assets must be embedded/same-origin');
 console.log('Admin client: read-only load, dirty edit protection, confirmed save+sync, manual wake/off, validation and honest write failure passed');
})().catch(e=>{console.error(e);process.exit(1)});
