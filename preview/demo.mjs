// Synthetic UI fixtures. These are NOT any family member's real plan or weights.
export const demoProfiles=[{slug:'alex',name:'Alex'},{slug:'blair',name:'Blair'},{slug:'casey',name:'Casey'},{slug:'drew',name:'Drew'}];
const exercises={
 bench:['Manualbenk','0289-SpYC0Kp','dumbbell'],squat:['Stangknebøy','0043-qXTaZnJ','barbell'],
 row:['Sittende kabelroing','0861-fUBheHs','cable'],pulldown:['Nedtrekk','0818-rkg41Fb','cable'],
 goblet:['Goblet squat','1760-yn8yg1r','dumbbell'],bug:['Dead bug','0276-iny3m5y','body weight'],
 pallof:['Pallof press','0979-9pa4H5m','band'],
};
function entry(key,count,reps,weight,restSeconds=90){
 const [name,file,equipment]=exercises[key],bodyweight=['body weight','band'].includes(equipment);
 return {name,equipment,mode:'reps',unit:'kg',bodyweight,perSide:key==='bug',restSeconds,
  target:`${count} × ${reps}`,load:bodyweight?'Kroppsvekt':weight===null?'Valgfri vekt':`${weight} kg`,
  detail:key==='bug'?`${reps/2} per side · ${reps} totalt`:'',note:'',
  image:`/media/img/${file}.jpg`,animation:`/media/gif/${file}.gif`,
  sets:Array.from({length:count},()=>({warmup:false,weight:bodyweight?0:weight,reps,seconds:0,minutes:0,speed:0}))};
}
const plans={
 alex:{days:[0,1,3,5],title:'Helkropp A',entries:[entry('bench',3,12,32),entry('row',3,10,30),entry('squat',3,8,40,120),entry('pulldown',3,10,25),entry('pallof',2,12,0),entry('bug',2,16,0)]},
 blair:{days:[0,2,4],title:'Helkropp B',entries:[entry('goblet',3,10,8),entry('bench',3,10,12),entry('row',3,12,15),entry('bug',2,12,0)]},
 casey:{days:[0,2,5],title:'Styrke A',entries:[entry('pulldown',2,10,15),entry('goblet',2,10,null),entry('bench',2,10,10),entry('pallof',2,12,0)]},
 drew:{days:[0,3,5],title:'Styrke B',entries:[entry('row',2,10,10),entry('goblet',2,10,null),entry('bug',2,12,0)]},
};
export function demoPlan(slug,day=null,now=new Date()){
 const p=plans[slug],person=demoProfiles.find(x=>x.slug===slug);if(!p||!person)throw Error('Unknown demo profile');
 const date=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Oslo',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
 const dt=new Date(date+'T12:00:00Z'),todayIndex=(dt.getUTCDay()+6)%7;
 day??=p.days[0];dt.setUTCDate(dt.getUTCDate()+day-todayIndex);const active=p.days.includes(day);
 return {schema:1,profile:person.name,profileSlug:slug,date:dt.toISOString().slice(0,10),day,todayIndex,
  title:active?p.title:'Hviledag',state:active?'planned':'rest',week:Array.from({length:7},(_,i)=>p.days.includes(i)),
  revision:`demo-${slug}-${day}`,entries:active?structuredClone(p.entries):[]};
}
