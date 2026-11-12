import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const cwd=fileURLToPath(new URL('..',import.meta.url));
function dates(env={}) {
  return spawnSync(process.execPath,['--input-type=module','-e',`
    import {localDate,selectedDate} from './bridge/model.mjs';
    console.log(JSON.stringify([localDate(new Date('2026-10-26T00:15:00Z')),selectedDate(null,new Date('2026-10-26T00:15:00Z')),localDate(new Date('2026-10-25T02:30:00Z'))]));
  `],{cwd,env:{...process.env,PANEL_TIMEZONE:'Europe/Oslo',PANEL_LANGUAGE:'nb',...env},encoding:'utf8'});
}
test('default timezone preserves installed Norwegian date and weekday semantics',()=>{
  const r=dates();assert.equal(r.status,0,r.stderr);
  assert.deepEqual(JSON.parse(r.stdout),['2026-10-26',{date:'2026-10-26',todayIndex:0,day:0},'2026-10-25']);
});
test('timezone override changes both local date and planned weekday at the same boundary',()=>{
  const r=dates({PANEL_TIMEZONE:'America/New_York'});assert.equal(r.status,0,r.stderr);
  assert.deepEqual(JSON.parse(r.stdout),['2026-10-25',{date:'2026-10-25',todayIndex:6,day:6},'2026-10-24']);
});
test('bad timezone or unimplemented UI language fails explicitly rather than guessing',()=>{
  assert.notEqual(dates({PANEL_TIMEZONE:'Not/A_Zone'}).status,0);
  assert.notEqual(dates({PANEL_TIMEZONE:''}).status,0);
  assert.notEqual(dates({PANEL_LANGUAGE:'fr'}).status,0);
});

test('English uses the same dates and timezone rules as Norwegian', () => {
  const result = dates({ PANEL_LANGUAGE: 'en' });
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), JSON.parse(dates().stdout));
});
