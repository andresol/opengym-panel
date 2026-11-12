import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {makePreviewServer} from '../preview/server.mjs';
import {snapshot} from '../bridge/model.mjs';
import {demoProfiles,demoPlan} from '../preview/demo.mjs';
const now=()=>new Date('2026-10-13T19:00:00Z');
const base=(name='A',weight=20)=>({unit:'kg',week:{2:'r1'},dayPlan:{},workouts:[],customEx:[],exNotes:{},routines:[{id:'r1',name,ex:[{id:'0043',sets:2,reps:10,weight,prog:'off',restSec:120}]}]});
test('profile projection is synchronous, isolated, sanitised and does not mutate any state',()=>{
 const a=base('A',23),b=base('B',7);a.customEx=[{id:'0043',n:'Only A',img:'https://secret.invalid/personal.jpg',eq:'barbell'}];
 const beforeA=JSON.stringify(a),beforeB=JSON.stringify(b);
 for(let i=0;i<6;i++){
  const pa=snapshot(a,1,now(),{enhanced:true,profile:'Alpha'}),pb=snapshot(b,1,now(),{enhanced:true,profile:'Beta'});
  assert.equal(pa.profile,'Alpha');assert.equal(pb.profile,'Beta');assert.equal(pa.entries[0].name,'Only A');assert.equal(pb.entries[0].name,'barbell full squat');assert.equal(pa.entries[0].sets[0].weight,23);assert.equal(pb.entries[0].sets[0].weight,7);
  assert.equal(pa.entries[0].image,null);assert.equal(pb.entries[0].image,'/media/img/v140-0043.jpg');assert(!JSON.stringify(pa).includes('secret.invalid'));
 }
 assert.equal(JSON.stringify(a),beforeA);assert.equal(JSON.stringify(b),beforeB);
 const c=base();c.customEx=[{id:'new',n:'Custom',eq:'barbell'}];c.routines[0].ex[0].id='new';
 assert.equal(snapshot(c,1,now(),{enhanced:true}).entries[0].image,null);
 assert.equal(snapshot(c,1,now(),{enhanced:true,mediaAliases:{new:'0043'}}).entries[0].image,'/media/img/v140-0043.jpg');
});
test('four demo profiles have distinct plans, real catalogue illustrations and honest rest days',()=>{
 const revisions=new Set(),plans=[];
 for(const p of demoProfiles){const d=demoPlan(p.slug,null,now());revisions.add(d.revision);plans.push(d.entries);assert.equal(d.profile,p.name);assert(d.entries.length);assert(d.entries.every(e=>e.image&&e.animation&&e.sets.length));
  for(let day=0;day<7;day++){const s=demoPlan(p.slug,day,now());assert.equal(s.day,day);assert.equal(s.state==='planned',s.week[day]);if(!s.week[day])assert.equal(s.entries.length,0);}}
 assert.equal(revisions.size,4);assert.notDeepEqual(plans[0],plans[1]);assert.throws(()=>demoPlan('unknown'));assert.equal(demoPlan('alex',0,now()).date,'2026-10-12');
});
test('preview API allowlist/auth/media/methods and profile failure isolation',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'gym-preview-test-')),token='test-'.repeat(8);
 const files=['fixeduser1','fixeduser2'].map(uid=>path.join(dir,`state-${uid}.json`));
 fs.writeFileSync(files[0],JSON.stringify(base('Only Alpha',23)));fs.writeFileSync(files[1],JSON.stringify(base('Only Beta',7)));
 const server=makePreviewServer({token,profiles:[{slug:'alpha',name:'Alpha',uid:'fixeduser1'},{slug:'beta',name:'Beta',uid:'fixeduser2'}],dataDir:dir,now});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url=`http://127.0.0.1:${server.address().port}`,headers={Authorization:`Bearer ${token}`};
 const get=(route,auth=true,method='GET')=>fetch(url+route,{headers:auth?headers:{},method});
 try{
  for(const route of ['/api/profiles','/api/profiles/alpha/plan'])assert.equal((await get(route,false)).status,401);
  const profiles=await(await get('/api/profiles')).json();assert.deepEqual(profiles.profiles,[{slug:'alpha',name:'Alpha'},{slug:'beta',name:'Beta'}]);
  for(let i=0;i<3;i++)for(const [slug,name,w] of [['alpha','Alpha',23],['beta','Beta',7]]){
   const r=await get(`/api/profiles/${slug}/plan?day=1`);assert.equal(r.status,200);const p=await r.json();assert.equal(p.profile,name);assert.equal(p.profileSlug,slug);assert.equal(p.entries[0].sets[0].weight,w);assert.equal(p.entries[0].name,'Stangknebøy');assert(!JSON.stringify(p).includes('fixeduser'));assert(!JSON.stringify(p).includes(token));}
  for(const q of ['?uid=fixeduser2','?day=1&day=2','?day=7','?day=1.0','?day=','?profile=beta'])assert.equal((await get('/api/profiles/alpha/plan'+q)).status,400);
  assert.equal((await get('/api/profiles/admin/plan')).status,404);assert.equal((await get('/api/profiles/alpha/plan',true,'POST')).status,405);
  assert.equal((await get('/media/img/v140-0043.jpg',false)).status,200);assert.equal((await get('/media/img/private.jpg',false)).status,404);
  assert.equal((await get('/config.json',false)).status,404);assert.equal((await get('/names.mjs',false)).status,404);
  fs.writeFileSync(files[1],'{broken');assert.equal((await get('/api/profiles/beta/plan')).status,503);assert.equal((await get('/api/profiles/alpha/plan')).status,200);
  fs.unlinkSync(files[1]);fs.symlinkSync(files[0],files[1]);assert.equal((await get('/api/profiles/beta/plan')).status,503);
 }finally{server.closeAllConnections();await new Promise(r=>server.close(r));fs.rmSync(dir,{recursive:true,force:true});}
});
