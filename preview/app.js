import {demoProfiles,demoPlan} from './demo.mjs';
const $=id=>document.getElementById(id),days=['Man','Tir','Ons','Tor','Fre','Lør','Søn'];
let people=demoProfiles,person=null,plan=null,index=0,day=null,live=false,token='',generation=0,abort=null;
let seconds=0,deadline=0,lastSuccess=0,playing=false,loading=false;
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;};
const number=v=>Number(v).toLocaleString('nb-NO',{maximumFractionDigits:2});
const selected=()=>plan?.entries[index];
function status(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
function connection(){ $('connection').textContent=live?'Live':'Demo';$('connection').classList.toggle('live',live); }
function remaining(){return deadline?Math.max(0,Math.ceil((deadline-performance.now())/1000)):seconds;}
function drawTimer(){let r=remaining();if(deadline&&!r){deadline=0;seconds=0;status(live?'Pausen er ferdig · live plan, ingen logging':'Pausen er ferdig · eksempeldata');}
 $('timer').textContent=`${Math.floor(r/60).toString().padStart(2,'0')}:${(r%60).toString().padStart(2,'0')}`;
 $('timer-start').textContent=deadline?'Stopp pause':r?'Start pause':'Start på nytt';$('timer-start').classList.toggle('running',!!deadline);
}
function resetTimer(){deadline=0;seconds=selected()?.restSeconds??0;drawTimer();}
function clearPlan(){plan=null;index=0;playing=false;lastSuccess=0;resetTimer();render();}
function cards(container){
 container.replaceChildren();
 for(const p of people){const b=el('button','profile-card');b.setAttribute('aria-label',`Velg ${p.name}`);b.append(el('span','avatar',p.name.slice(0,1)),el('strong','',p.name),el('span','',live?'Treningsplan →':'Eksempeløkt →'));b.onclick=()=>selectPerson(p);container.append(b);}
}
function renderPeople(){cards($('profiles'));cards($('profile-options'));connection();}
async function selectPerson(p){
 person=p;day=null;loading=true;clearPlan();$('welcome').hidden=true;$('workout').hidden=false;
 $('profile-dialog').close();$('person-name').textContent=p.name;$('avatar').textContent=p.name.slice(0,1);await load();
}
function rowLoad(s,e){if(e.mode==='time'||e.mode==='cardio')return '';if(e.bodyweight&&s.weight===0)return 'Kroppsvekt';return s.weight===null?'Valgfri vekt':`${number(s.weight)} ${e.unit||'kg'}`;}
function rowTarget(s,e){return e.mode==='time'?`${number(s.seconds)} s`:e.mode==='cardio'?`${number(s.minutes)} min`:`${number(s.reps)} reps`;}
function renderMedia(){
 const e=selected(),img=$('exercise-image'),src=playing?e?.animation:e?.image;
 if(!src){img.hidden=true;img.removeAttribute('src');$('media-empty').hidden=false;$('animate').hidden=true;
  $('media-message').textContent=e?'Ingen illustrasjon for denne øvelsen':loading?'Henter økt …':plan?.state==='rest'?'Ingen planlagt styrkeøkt':'Økten er utilgjengelig';return;}
 img.hidden=false;$('media-empty').hidden=true;img.alt=`${playing?'Animasjon':'Illustrasjon'}: ${e.name}`;
 if(img.getAttribute('src')!==src)img.src=src;
 $('animate').hidden=!e.animation;$('animate').textContent=playing?'Stopp animasjon':'Spill animasjon';$('animate').setAttribute('aria-pressed',String(playing));
}
function render(){
 const e=selected(),list=$('exercise-list');
 $('plan-owner').textContent=person?`${person.name.toLocaleUpperCase('nb-NO')} · ${plan?new Date(plan.date+'T12:00:00Z').toLocaleDateString('nb-NO',{weekday:'long',day:'numeric',month:'long'}):'TRENINGSPLAN'}`:'';
 $('routine').textContent=plan?.title||(loading?'Henter økt …':'OpenGym utilgjengelig');
 $('position').textContent=e?`ØVELSE ${index+1} AV ${plan.entries.length}`:plan?.state==='rest'?'HVILEDAG':'';
 $('exercise').textContent=e?.name||(plan?.state==='rest'?'Tid til å hente seg inn':loading?'':'Kunne ikke hente økten');
 $('exercise-count').textContent=plan?String(plan.entries.length):'';
 list.replaceChildren();
 for(const [i,x] of (plan?.entries||[]).entries()){
  const b=el('button','exercise-item'+(i===index?' selected':''));b.setAttribute('aria-label',`${i+1}. ${x.name}`);b.setAttribute('aria-current',i===index?'step':'false');
  const text=el('span');text.append(el('strong','',x.name),el('small','',x.target));b.append(el('span','number',String(i+1).padStart(2,'0')),text);b.onclick=()=>chooseExercise(i);list.append(b);
 }
 $('list-footer').textContent=plan?.state==='rest'?'Ingen styrkeøkt denne dagen.':'';
 const work=e?.sets?.filter(s=>!s.warmup)||[],first=work[0];
 $('set-count').textContent=e?String(work.length):'—';
 const load=first?rowLoad(first,e):'';$('load').textContent=load||'—';$('load').classList.toggle('text-value',load.length>7);
 $('target-label').textContent=e?.mode==='reps'?'REPETISJONER':'VARIGHET';
 $('target').textContent=first?(e.mode==='time'?`${number(first.seconds)} s`:e.mode==='cardio'?`${number(first.minutes)} min`:number(first.reps)):'—';
 $('detail').textContent=e?.detail||'';$('note').textContent=e?.note||'';
 $('sets').replaceChildren();let workIndex=0,warmupIndex=0;
 for(const s of e?.sets||[]){const r=el('div','set-row'+(s.warmup?' warmup':''));r.append(el('span','',s.warmup?`Oppv. ${++warmupIndex}`:`Sett ${++workIndex}`),el('span','',rowLoad(s,e)),el('span','',rowTarget(s,e)));$('sets').append(r);}
 $('prev').disabled=!e||index===0;$('next').disabled=!e||index===plan.entries.length-1;
 for(const id of ['minus','plus','timer-reset','timer-start'])$(id).disabled=!e;
 [...$('week').children].forEach((b,i)=>{b.classList.toggle('selected',i===(plan?.day??day));b.classList.toggle('scheduled',!!plan?.week[i]);b.setAttribute('aria-pressed',String(i===(plan?.day??day)));});
 renderMedia();
}
function chooseExercise(i){if(!plan?.entries[i])return;index=i;playing=false;resetTimer();render();$('exercise-list').children[i]?.scrollIntoView({block:'nearest'});}
async function load(){
 if(!person)return;
 const id=++generation,p=person,requestedDay=day;abort?.abort();const controller=new AbortController();abort=controller;
 const timeout=setTimeout(()=>controller.abort(),6000);loading=true;status('Henter økt …');
 try{
  let next;if(live){const r=await fetch(`/api/profiles/${encodeURIComponent(p.slug)}/plan${requestedDay===null?'':'?day='+requestedDay}`,{headers:{Authorization:`Bearer ${token}`},signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('fetch');next=await r.json();}
  else next=demoPlan(p.slug,requestedDay);
  if(id!==generation)return;
  if(next.profileSlug!==p.slug||next.profile!==p.name)throw Error('Wrong profile');
  const changed=next.revision!==plan?.revision||next.date!==plan?.date;plan=next;day=next.day;loading=false;lastSuccess=performance.now();
  if(changed){index=0;playing=false;resetTimer();}render();connection();
  status(live?'Live plan · ingen treningslogging':'Forhåndsvisning · eksempeldata · ingen treningslogging');
 }catch{if(id===generation){loading=false;clearPlan();$('connection').textContent=live?'Frakoblet':'Demo';status('Kunne ikke hente økten · ingen ferske treningsdata',true);}}
 finally{clearTimeout(timeout);}
}
for(const [i,label] of days.entries()){const b=el('button','',label);b.onclick=()=>{day=i;loading=true;clearPlan();load();};$('week').append(b);}
$('prev').onclick=()=>chooseExercise(index-1);$('next').onclick=()=>chooseExercise(index+1);
$('animate').onclick=()=>{playing=!playing;renderMedia();};
$('exercise-image').onerror=()=>{const e=selected();if(playing&&e?.image){playing=false;renderMedia();return;}$('exercise-image').hidden=true;$('media-empty').hidden=false;$('media-message').textContent='Illustrasjonen er utilgjengelig';$('animate').hidden=true;};
$('timer-start').onclick=()=>{if(deadline){seconds=remaining();deadline=0;}else{if(!seconds)seconds=selected()?.restSeconds||90;deadline=performance.now()+seconds*1000;}drawTimer();};
$('timer-reset').onclick=resetTimer;
for(const [id,delta] of [['minus',-15],['plus',15]])$(id).onclick=()=>{seconds=Math.max(0,Math.min(3600,remaining()+delta));if(deadline)deadline=seconds?performance.now()+seconds*1000:0;drawTimer();};
$('person').onclick=()=>{renderPeople();$('profile-dialog').showModal();};$('profile-close').onclick=()=>$('profile-dialog').close();
$('connection').onclick=()=>{$('connect-error').textContent='';$('connect-dialog').showModal();};$('cancel').onclick=()=>$('connect-dialog').close();
function returnToPicker(){++generation;abort?.abort();person=null;day=null;loading=false;clearPlan();$('welcome').hidden=false;$('workout').hidden=true;$('person-name').textContent='Velg person';$('avatar').textContent='+';renderPeople();}
$('demo-mode').onclick=()=>{live=false;token='';people=demoProfiles;returnToPicker();$('connect-dialog').close();status('Forhåndsvisning · eksempeldata · ingen treningslogging');};
$('connect-form').onsubmit=async ev=>{
 ev.preventDefault();const candidate=$('token').value.trim();$('token').value='';const submit=$('connect-form').querySelector('[type="submit"]');submit.disabled=true;
 // Immediately discard the previous person's values while changing authentication context.
 const id=++generation;abort?.abort();loading=true;clearPlan();const controller=new AbortController();abort=controller;const timeout=setTimeout(()=>controller.abort(),6000);
 try{const r=await fetch('/api/profiles',{headers:{Authorization:`Bearer ${candidate}`},signal:controller.signal,cache:'no-store'});if(!r.ok)throw Error('auth');const data=await r.json();if(id!==generation)return;if(!data.profiles?.length)throw Error('profiles');token=candidate;live=true;people=data.profiles;returnToPicker();$('connect-dialog').close();status('Live plan · velg person');}
 catch{if(id===generation){loading=false;$('connect-error').textContent='Kunne ikke koble til. Kontroller panelnøkkelen.';status('Tilkoblingen mislyktes · ingen ferske treningsdata',true);}}
 finally{clearTimeout(timeout);submit.disabled=false;}
};
setInterval(()=>{drawTimer();if(live&&lastSuccess&&performance.now()-lastSuccess>70000){clearPlan();$('connection').textContent='Frakoblet';status('Frakoblet · ingen ferske treningsdata',true);}},200);
setInterval(()=>{if(person&&!$('connect-dialog').open&&!$('profile-dialog').open)load();},30000);
renderPeople();
