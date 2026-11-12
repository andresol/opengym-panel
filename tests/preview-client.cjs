// DOM-level behaviour tests, not a rendered browser/physical-screen check.
// Uses an existing local linkedom install. No browser or network navigation.
const {parseHTML}=require(process.env.LINKEDOM_MODULE||'linkedom');
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const {demoProfiles,demoPlan}=await import('../preview/demo.mjs');
 const {window,document}=parseHTML(fs.readFileSync(path.join(__dirname,'../preview/index.html'),'utf8'));
 const $=id=>document.getElementById(id);let now=0,requests=[],ticks=[];
 window.HTMLElement.prototype.scrollIntoView=function(){};
 for(const d of document.querySelectorAll('dialog')){d.showModal=function(){this.open=true;};d.close=function(){this.open=false;};}
 const ctx={document,console,demoProfiles,demoPlan,performance:{now:()=>now},Date,Number,String,Math,encodeURIComponent,AbortController,structuredClone,
  setTimeout:()=>0,clearTimeout:()=>{},setInterval:fn=>ticks.push(fn),fetch:(url,options)=>new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../preview/app.js'),'utf8').replace(/^import .*?;\n/,''),ctx);
 const settle=async()=>{for(let n=0;n<12;n++)await Promise.resolve();};
 const select=async(i)=>{await $('profiles').children[i].onclick();await settle();};
 const respond=(r,p,status=200)=>r.resolve({ok:status===200,status,json:async()=>p});
 assert.equal($('profiles').children.length,4);await select(0);assert.equal($('person-name').textContent,'Alex');assert.equal($('exercise').textContent,'Manualbenk');assert.equal($('load').textContent,'32 kg');assert.equal($('exercise-list').children.length,6);
 $('animate').onclick();assert($('exercise-image').getAttribute('src').endsWith('.gif'));$('animate').onclick();assert($('exercise-image').getAttribute('src').endsWith('.jpg'));
 $('timer-start').onclick();now=2000;ticks[0]();assert.equal($('timer').textContent,'01:28');$('timer-start').onclick();now=5000;ticks[0]();assert.equal($('timer').textContent,'01:28');$('plus').onclick();assert.equal($('timer').textContent,'01:43');$('timer-reset').onclick();assert.equal($('timer').textContent,'01:30');
 $('next').onclick();assert.equal($('exercise').textContent,'Sittende kabelroing');$('exercise-list').children[2].onclick();assert.equal($('exercise').textContent,'Stangknebøy');assert.equal($('timer').textContent,'02:00');
 for(let i=1;i<4;i++){await select(i);assert.equal($('person-name').textContent,demoProfiles[i].name);assert.equal($('exercise-list').children.length,demoPlan(demoProfiles[i].slug).entries.length);assert.equal($('timer-start').textContent,'Start pause');}
 $('week').children[6].onclick();await settle();assert.equal($('routine').textContent,'Hviledag');assert($('timer-start').disabled);assert.equal($('load').textContent,'—');assert($('exercise-image').hidden);
 $('token').value='test-preview-key-not-real-'.repeat(2);const connect=$('connect-form').onsubmit({preventDefault(){}});respond(requests.shift(),{profiles:demoProfiles});await connect;assert.equal($('connection').textContent,'Live');
 // A stale response for Alex must never replace Blair, even if fetch ignores abort.
 const a=$('profiles').children[0].onclick(),old=requests.shift();assert.equal($('load').textContent,'—');
 const b=$('profiles').children[1].onclick(),fresh=requests.shift();assert.equal($('person-name').textContent,'Blair');assert.equal($('load').textContent,'—');
 respond(fresh,demoPlan('blair'));await b;respond(old,demoPlan('alex'));await a;assert.equal($('exercise').textContent,'Goblet squat');assert.equal($('load').textContent,'8 kg');
 // A failing profile must clear every previous name/value/image, without data fallback.
 const c=$('profiles').children[2].onclick();assert.equal($('load').textContent,'—');assert.equal($('exercise-list').children.length,0);respond(requests.shift(),{},503);await c;assert.equal($('person-name').textContent,'Casey');assert.equal($('load').textContent,'—');assert($('exercise-image').hidden);assert($('timer-start').disabled);
 $('week').children[0].onclick();respond(requests.shift(),demoPlan('casey',0));await settle();assert.equal($('exercise').textContent,'Nedtrekk');assert.equal($('load').textContent,'15 kg');
 // Wrong-profile responses also fail closed.
 $('week').children[2].onclick();respond(requests.shift(),demoPlan('alex',2));await settle();assert.equal($('load').textContent,'—');assert($('timer-start').disabled);
 $('week').children[0].onclick();respond(requests.shift(),demoPlan('casey',0));await settle();now+=71000;ticks[0]();assert.equal($('load').textContent,'—');assert.equal($('connection').textContent,'Frakoblet');
 $('demo-mode').onclick();assert.equal($('connection').textContent,'Demo');await select(0);$('exercise-image').onerror();assert($('exercise-image').hidden);assert.equal($('media-message').textContent,'Illustrasjonen er utilgjengelig');
 const report={domOnly:true,renderedBrowser:false,profiles:4,exerciseList:true,mediaToggle:true,timerCountdownPauseAdjustReset:true,restDay:true,profileRaceIsolation:true,offlineClearsAllData:true,recovery:true,wrongProfileRejected:true,staleDataExpires:true,missingImageHonest:true};console.log(JSON.stringify(report,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
