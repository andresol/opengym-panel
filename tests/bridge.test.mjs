import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {snapshot,selectedDate} from '../bridge/model.mjs';
import {makeServer} from '../bridge/server.mjs';
const now=()=>new Date('2026-10-13T18:00:00Z');
const base=()=>({unit:'kg',week:{2:['r1']},dayPlan:{},workouts:[],customEx:[],exNotes:{},routines:[{id:'r1',name:'Bein',ex:[{id:'0043',sets:2,reps:10,weight:0,prog:'off',restSec:120}]}]});
test('Oslo date and Monday indexed week cross UTC midnight and DST',()=>{
 assert.equal(selectedDate(null,new Date('2026-10-13T22:30:00Z')).date,'2026-10-14');
 assert.equal(selectedDate(0,new Date('2026-10-25T23:30:00Z')).date,'2026-10-26');
 assert.equal(selectedDate(6,now()).date,'2026-10-18');assert.throws(()=>selectedDate(9,now()));
});
test('native prescription, open weight and custom exercise stay separate',()=>{
 const s=base();s.customEx=[{id:'mine',n:'Lette avslutningssett',bp:'upper legs',eq:'barbell'}];s.routines[0].ex.push({id:'mine',sets:2,reps:10,weight:0,prog:'off',restSec:120});
 const copy=JSON.stringify(s),p=snapshot(s,null,now());assert.equal(JSON.stringify(s),copy);assert.equal(p.entries.length,2);assert.equal(p.entries[1].name,'Lette avslutningssett');assert.equal(p.entries[1].load,'Valgfri vekt');assert.equal(p.entries[1].sets.length,2);assert.equal(p.entries[1].sets[0].weight,null);assert.equal(p.entries[0].restSeconds,120);
 assert(!JSON.stringify(p).includes('r1'));assert(!JSON.stringify(p).includes('workouts'));
});
test('rest override, combined routines and empty state fail honestly',()=>{
 const s=base();s.dayPlan['2026-10-13']='rest';assert.equal(snapshot(s,null,now()).state,'rest');delete s.dayPlan['2026-10-13'];s.routines.push({id:'r2',name:'Kjerne',ex:[{id:'0043',sets:1,reps:8,weight:20,prog:'off'}]});s.week[2]=['r1','r2'];assert.equal(snapshot(s,null,now()).entries.length,2);assert.throws(()=>snapshot({},null,now()));
});
test('linear progression uses native history; per side repetitions are total',()=>{
 const s=base();s.routines[0].ex[0]={id:'0043',sets:2,reps:8,weight:20,prog:'linear',inc:2.5,side:true};s.workouts=[{routineId:'r1',d:'2026-10-06',entries:[{id:'0043',target:{sets:2,reps:8,weight:20},sets:[{w:20,r:8,done:true},{w:20,r:8,done:true}]}]}];
 const p=snapshot(s,null,now());assert.equal(p.entries[0].sets[0].weight,22.5);assert.match(p.entries[0].detail,/4 per side · 8 totalt/);
});
test('HTTP auth, strict profile binding, methods, failure, atomic state replacement',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'gym-panel-test-'));const file=path.join(dir,'state-testuser1.json');fs.writeFileSync(file,JSON.stringify(base()));fs.writeFileSync(path.join(dir,'state-otheruser.json'),JSON.stringify({...base(),routines:[]}));
 const token='test-secret-'.repeat(4);const server=makeServer({token,uid:'testuser1',dataDir:dir,now});await new Promise(r=>server.listen(0,'127.0.0.1',r));const url=`http://127.0.0.1:${server.address().port}`;const headers={Authorization:`Bearer ${token}`};
 try{
  assert.equal((await fetch(url+'/api/plan')).status,401);
  for(const q of ['?uid=otheruser','?day=1&uid=x','?day=1&day=2','?day=99','?day=','?day=1.0'])assert.equal((await fetch(url+'/api/plan'+q,{headers})).status,400);
  assert.equal((await fetch(url+'/api/plan',{method:'POST',headers})).status,405);
  const first=await fetch(url+'/api/plan',{headers});assert.equal(first.status,200);assert.equal((await first.json()).profile,'User');
  const s=base();s.routines[0].name='Ny plan';fs.writeFileSync(file+'.tmp',JSON.stringify(s));fs.renameSync(file+'.tmp',file);assert.equal((await (await fetch(url+'/api/plan',{headers})).json()).title,'Ny plan');
  fs.writeFileSync(file,'{broken');assert.equal((await fetch(url+'/api/plan',{headers})).status,503);
  fs.unlinkSync(file);fs.symlinkSync(path.join(dir,'state-otheruser.json'),file);assert.equal((await fetch(url+'/api/plan',{headers})).status,503);
  assert.equal((await fetch(url+'/.env')).status,404);
 }finally{server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(dir,{recursive:true,force:true});}
});
