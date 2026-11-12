import crypto from 'node:crypto';
import { buildSessionEntries } from '../vendor/opengym/frontend/src/lib/session-start.js';
import { effectiveRoutines, modeOf, isBw } from '../vendor/opengym/frontend/src/lib/history.js';
import { exOr, registerCustom, CATALOGUE, canonicalExId } from '../vendor/opengym/frontend/src/lib/exercises.js';
import { isWarmupRow } from '../vendor/opengym/frontend/src/lib/workout-model.js';
import { equipmentState, equipmentEntries, cableControls } from './equipment.mjs';
import { musclesOf, MUSCLES } from '../vendor/opengym/frontend/src/lib/muscles.js';
import { mediaAsset } from './catalogue-media.mjs';
import { LANGUAGE, text } from './language.mjs';
export { LANGUAGE } from './language.mjs';
export const VERSION = '1.4.4';
export const clean = (v, max=120) => typeof v === 'string' ? v.replace(/[\x00-\x1f\x7f]/g,' ').trim().slice(0,max) : '';
export const num = (v, max=10000) => Number.isFinite(Number(v)) ? Math.max(0, Math.min(max, Number(v))) : 0;
export const TIME_ZONE = process.env.PANEL_TIMEZONE ?? 'Europe/Oslo';
try { new Intl.DateTimeFormat('en', {timeZone: TIME_ZONE}).format(0); }
catch { throw new Error('Invalid PANEL_TIMEZONE'); }
export function localDate(now=new Date()) {
  return new Intl.DateTimeFormat('sv-SE',{timeZone:TIME_ZONE,year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
}
export function selectedDate(day, now=new Date()) {
  const today=localDate(now), d=new Date(today+'T12:00:00Z');
  const todayIndex=(d.getUTCDay()+6)%7;
  if(day!=null && (!Number.isInteger(day)||day<0||day>6)) throw new Error('invalid day');
  if(day!=null) d.setUTCDate(d.getUTCDate()+day-todayIndex);
  return {date:d.toISOString().slice(0,10),todayIndex,day:day??todayIndex};
}
export function snapshot(raw, day=null, now=new Date(), options={}) {
  if(!raw || !Array.isArray(raw.routines) || !Array.isArray(raw.workouts)) throw new Error('invalid state');
  const {date,todayIndex,day:dayIndex}=selectedDate(day,now);
  const state=equipmentState({...raw,active:{d:date},week:raw.week||{},dayPlan:raw.dayPlan||{},customEx:raw.customEx||[]});
  // This entire projection is synchronous: clear and re-register ONLY this profile's catalogue.
  registerCustom(state.customEx);
  const routines=effectiveRoutines(state,date);
  if(routines.length>4) throw new Error('too many routines');
  const entries=[];
  for(const routine of routines) {
    if(!Array.isArray(routine.ex)||routine.ex.length>40) throw new Error('invalid routine');
    for(const e of equipmentEntries(state,buildSessionEntries(state,routine))) {
      const cfg=e.target||{}, known=state.customEx.find(x=>x.id===e.id)||exOr(e.id);
      const rows=e.sets||[], work=rows.filter(x=>!isWarmupRow(x));
      const mode=modeOf(cfg), bodyweight=isBw(cfg);
      const unit=state.unit==='lb'?'lb':'kg';
      const first=work[0]||{}, weight=num(first.w);
      const openWeight=!bodyweight && weight===0 && num(cfg.weight)===0;
      const sets=work.length, reps=num(first.r), seconds=num(first.sec), minutes=num(first.min);
      const target=mode==='time'?`${sets} × ${seconds} ${text('sek', 'sec')}`:mode==='cardio'?`${minutes} min`:`${sets} × ${reps}`;
      const load=openWeight?text('Valgfri vekt', 'Choose weight'):weight>0?`${weight} ${unit}`:bodyweight?text('Kroppsvekt', 'Bodyweight'):text('Uten ekstra vekt', 'No added weight');
      const warmups=rows.filter(isWarmupRow).length;
      const restSeconds=cfg.restSec==null?90:num(cfg.restSec,3600);
      const detail=[mode==='reps'&&cfg.side?`${reps/2} per side · ${reps} ${text('totalt', 'total')}`:null,
        warmups?`${warmups} ${text('oppvarmingssett', warmups === 1 ? 'warm-up set' : 'warm-up sets')}`:null,
        `${text('Pause', 'Rest')} ${restSeconds} ${text('sek', 'sec')}`].filter(Boolean).join(' · ');
      // No raw ids, progression objects, complete workouts, or bodyweight history on the wire.
      const entry={name:clean(known.n||known.name),target,load,detail,
        note:clean(cfg.note||state.exNotes?.[e.id],250),restSeconds,
        sets:rows.slice(0,24).map(s=>({warmup:isWarmupRow(s),weight:openWeight?null:num(s.w),reps:num(s.r),seconds:num(s.sec),minutes:num(s.min),speed:num(s.speed)}))};
      if(options.enhanced){
        const custom=state.customEx.some(x=>x.id===e.id);
        if(!custom&&LANGUAGE==='nb'&&options.names?.[e.id])entry.name=clean(options.names[e.id]);
        // Media can only come from the pinned public catalogue, never a state-supplied URL.
        const source=CATALOGUE.find(x=>x.id===canonicalExId(options.mediaAliases?.[e.id]||(!custom?e.id:null)));
        Object.assign(entry,{mode,unit,bodyweight,perSide:!!cfg.side,equipment:clean(known.eq),
          ...cableControls(state,e.id), muscles: MUSCLES.map(m => Math.min(1, musclesOf(known)[m] || 0)),
          image:mediaAsset('img',source),animation:mediaAsset('gif',source)});
      }
      entries.push(entry);
    }
  }
  if(entries.length>40) throw new Error('too many entries');
  const data={schema:1,version:VERSION,language:LANGUAGE,profile:clean(options.profile||'User',40),date,day:dayIndex,todayIndex,
    title:routines.map(x=>clean(x.name||x.n)).join(' + ').slice(0,160)||text('Hviledag', 'Rest day'),
    state:entries.length?'planned':'rest',entries,
    week:Array.from({length:7},(_,i)=>{const dt=selectedDate(i,now).date;return effectiveRoutines(state,dt).some(r=>r.ex?.length)>0;})};
  // Semantic revision is opaque and only covers the explicitly disclosed plan.
  data.revision=crypto.createHash('sha256').update(JSON.stringify(data)).digest('hex').slice(0,16);
  data.fetchedAt=now.toISOString();
  return data;
}
