const $=id=>document.getElementById(id), labels=['Man','Tir','Ons','Tor','Fre','Lør','Søn'];
let token='',demo=true,plan=null,index=0,day=null,requestId=0,abort=null,seconds=0,deadline=0,interval=null,lastSuccess=0;
function resize(){const s=Math.min(1,innerWidth/1280,innerHeight/800);$('panel').style.transform=`scale(${s})`;document.body.style.width=`${1280*s}px`;document.body.style.height=`${800*s}px`;document.body.style.minHeight='0';}
addEventListener('resize',resize);resize();
function remaining(){return deadline?Math.max(0,Math.ceil((deadline-performance.now())/1000)):seconds;}
function drawTimer(){let r=remaining();if(deadline&&r===0){deadline=0;seconds=0;}$('timer').textContent=`${Math.floor(r/60).toString().padStart(2,'0')}:${(r%60).toString().padStart(2,'0')}`;$('timer-start').textContent=deadline?'Stopp pause':r===0?'Start på nytt':'Start pause';}
function resetTimer(){deadline=0;seconds=plan?.entries[index]?.restSeconds??0;drawTimer();}
function render(){
  const e=plan?.entries[index];
  $('date').textContent=plan?new Date(plan.date+'T12:00:00Z').toLocaleDateString('nb-NO',{day:'numeric',month:'long'}):'';
  $('routine').textContent=plan?.title||'OpenGym utilgjengelig';$('position').textContent=e?`ØVELSE ${index+1} / ${plan.entries.length}`:'';
  $('exercise').textContent=e?.name||(plan?.state==='rest'?'Ingen planlagt styrkeøkt':'Kan ikke hente økten');
  for(const k of ['target','load','detail','note'])$(k).textContent=e?.[k]||'';
  $('prev').disabled=!e||index===0;$('next').disabled=!e||index>=plan.entries.length-1;
  for(const k of ['minus','plus','timer-start','timer-reset']) $(k).disabled=!e;
  [...$('week').children].forEach((b,i)=>{b.classList.toggle('selected',i===(plan?.day??day));b.classList.toggle('scheduled',!!plan?.week[i]);b.setAttribute('aria-pressed',String(i===(plan?.day??day)));});
}
function fail(){plan=null;resetTimer();render();$('connection').textContent='FRAKOBLET';$('connection').classList.remove('live');$('status').textContent='Frakoblet · ingen ferske treningsdata';}
async function load(){
  const id=++requestId;abort?.abort();abort=new AbortController();const timeout=setTimeout(()=>abort?.abort(),6000);
  $('status').textContent='Henter økt …';
  try{
    const r=await fetch(demo?'/demo.json':`/api/plan${day===null?'':'?day='+day}`,{headers:demo?{}:{Authorization:`Bearer ${token}`},signal:abort.signal,cache:'no-store'});
    if(!r.ok)throw Error('fetch');const next=await r.json();if(id!==requestId)return;
    if(demo&&day!==null){next.day=day;const d=new Date(next.date+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+day-1);next.date=d.toISOString().slice(0,10);if(!next.week[day]){next.title='Hviledag';next.entries=[];next.state='rest';}}
    const changed=next.revision!==plan?.revision||next.date!==plan?.date;plan=next;day=plan.day;lastSuccess=performance.now();if(changed){index=0;resetTimer();}render();
    $('status').textContent=demo?'Forhåndsvisning · eksempeldata':'Oppdatert · plan for neste øktstart';
    $('connection').textContent=demo?'DEMO':'TILKOBLET';$('connection').classList.toggle('live',!demo);
    if(!demo)$('connect-dialog').close();
  }catch(e){if(id===requestId){fail();if(!demo)$('connect-error').textContent='Kunne ikke koble til. Kontroller panelnøkkelen.';}}finally{clearTimeout(timeout);}
}
labels.forEach((label,i)=>{const b=document.createElement('button');b.textContent=label;b.onclick=()=>{day=i;load();};$('week').append(b);});
$('prev').onclick=()=>{if(index>0){index--;resetTimer();render();}};$('next').onclick=()=>{if(index+1<plan.entries.length){index++;resetTimer();render();}};
$('timer-start').onclick=()=>{if(deadline){seconds=remaining();deadline=0;}else{if(!seconds)seconds=plan?.entries[index]?.restSeconds||90;deadline=performance.now()+seconds*1000;}drawTimer();};
$('timer-reset').onclick=resetTimer;
for(const [id,delta] of [['minus',-15],['plus',15]])$(id).onclick=()=>{seconds=Math.min(3600,Math.max(0,remaining()+delta));if(deadline)deadline=seconds?performance.now()+seconds*1000:0;drawTimer();};
$('connection').onclick=()=>{$('connect-error').textContent='';$('connect-dialog').showModal();};$('cancel').onclick=()=>$('connect-dialog').close();
$('connect-form').onsubmit=e=>{e.preventDefault();token=$('token').value.trim();$('token').value='';demo=false;day=null;load();};
setInterval(()=>{drawTimer();if(!demo&&lastSuccess&&performance.now()-lastSuccess>70000){fail();lastSuccess=0;}},200);
setInterval(()=>{if(!$('connect-dialog').open)load();},30000);load();
