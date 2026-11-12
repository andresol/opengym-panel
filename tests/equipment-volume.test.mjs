import { test } from 'node:test';
import assert from 'node:assert/strict';
import { beginSession, panelView, editRow } from '../sessions/model.mjs';
import { snapshot } from '../bridge/model.mjs';
import { cableWeight, CABLE_WEIGHTS_KG, configureCableWeights } from '../bridge/equipment.mjs';
configureCableWeights([0, 4.5, 9.1, 13.6, 18.1, 22.7, 27.2, 31.8, 36.3, 40.8, 45.4, 50, 54.4, 59, 63.5, 68, 72.6, 77.1, 81.6, 86.2, 90.7, 95.3]);
const NOW = Date.parse('2026-11-01T12:00:00Z');
const binding = { slug: 'synthetic', name: 'Synthetic', uid: 'synthetic-only' };
const fixture = (id = '0861', weight = 9.1) => ({
  unit: 'kg', routines: [{ id: 'r', name: 'Synthetic', prog: 'linear', ex: [
    { id, weight, sets: 2, reps: 12, restSec: 90, prog: 'linear' },
  ] }], week: { 0: 'r' }, dayPlan: {}, workouts: [], customEx: [], bodyweight: [],
});

test('cable prescriptions/controls match explicitly configured labels, no source/history changes', () => {
  assert.deepEqual(CABLE_WEIGHTS_KG, [0, 4.5, 9.1, 13.6, 18.1, 22.7, 27.2, 31.8, 36.3, 40.8,
    45.4, 50, 54.4, 59, 63.5, 68, 72.6, 77.1, 81.6, 86.2, 90.7, 95.3]);
  for (const weight of CABLE_WEIGHTS_KG) assert.equal(cableWeight(weight), weight);
  assert.equal(cableWeight(4.55), 4.5);
  assert.equal(cableWeight(13.65), 13.6);
  assert.equal(cableWeight(100), 95.3);
  const raw = fixture('0861', 10.2), before = structuredClone(raw);
  const session = beginSession(raw, 6, NOW);
  const view = panelView(raw, binding, { session }, 6, NOW);
  assert.ok(Math.abs(view.entries[0].weightStep - 4.54) < 0.001);
  assert.equal(view.entries[0].weightMax, 95.3);
  assert.deepEqual(view.entries[0].weightOptions, CABLE_WEIGHTS_KG);
  assert.equal(view.entries[0].sets.find(s => !s.warmup).weight, 9.1);
  const plan = snapshot(raw, 6, new Date(NOW), { enhanced: true });
  assert.equal(plan.entries[0].sets.find(s => !s.warmup).weight, 9.1);
  assert.deepEqual(raw, before);
  assert.equal(view.session.volume, 0);
});

test('cable linear progression advances one actual plate; free weights/lb do not acquire stack', () => {
  const raw = fixture();
  raw.workouts = [{ id: 'old', d: '2026-10-25', routineIds: ['r'], entries: [{
    id: '0861', rid: 'r', target: raw.routines[0].ex[0], sets: [
      { w: 9.1, r: 12, done: true }, { w: 9.1, r: 12, done: true },
    ],
  }] }];
  const session = beginSession(raw, 6, NOW);
  assert.equal(session.active.entries[0].sets.find(s => !s.warmup).w, 13.6);
  for (const state of [fixture('0289', 7.25), { ...fixture(), unit: 'lb' }]) {
    const view = snapshot(state, 6, new Date(NOW), { enhanced: true });
    assert.equal(view.entries[0].weightStep, undefined);
  }
});

test('new calibration does not migrate existing draft results; direct edits preserve precision and completion', () => {
  const raw = fixture('0861', 13.65);
  let session = beginSession(raw, 6, NOW);
  session.active.entries[0].sets[0] = { w: 13.65, r: 12, done: true };
  const before = structuredClone(session);
  assert.equal(panelView(raw, binding, { session }, 6, NOW).entries[0].sets[0].weight, 13.65);
  assert.deepEqual(session, before);
  session = editRow(session, { exercise: 0, row: 1, weight: 7.35 });
  const row = session.active.entries[0].sets[1];
  assert.equal(row.w, 7.35);
  assert.equal(row.done, before.active.entries[0].sets[1].done);
  assert.deepEqual(session.active.entries[0].sets[0], before.active.entries[0].sets[0]);
});

test('confirmed volume excludes pending/warmups, counts sides independently and undo/edit updates it', () => {
  const raw = fixture('0289', 7.25);
  let session = beginSession(raw, 6, NOW);
  session.active.entries[0].sets = [
    { w: 100, r: 10, done: true, warmup: true },
    { w: 7.25, r: 12, done: true },
    { w: 20, r: 20, done: false },
    { w: 9, r: 20, done: false, sides: {
      L: { w: 4.55, r: 10, done: true }, R: { w: 9.1, r: 10, done: false },
    } },
  ];
  const volume = () => panelView(raw, binding, { session }, 6, NOW).session.volume;
  assert.equal(volume(), 132.5); // 87 + 45.5, never the mirrored aggregate.
  session = editRow(session, { exercise: 0, row: 3, side: 'R', done: true });
  assert.equal(volume(), 223.5);
  session = editRow(session, { exercise: 0, row: 1, done: false });
  assert.equal(volume(), 136.5);
  session = editRow(session, { exercise: 0, row: 3, side: 'L', weight: 9.1 });
  assert.equal(volume(), 182);
});

test('muscle vectors come from each selected profile/catalogue, never image aliases or another custom profile', () => {
  const raw = fixture();
  const plan = snapshot(raw, 6, new Date(NOW), { enhanced: true });
  const active = panelView(raw, binding, { session: beginSession(raw, 6, NOW) }, 6, NOW);
  assert.equal(plan.entries[0].muscles.length, 18);
  assert.deepEqual(plan.entries[0].muscles, active.entries[0].muscles);
  const custom = fixture('my-cable');
  custom.customEx = [{ id: 'my-cable', n: 'Synthetic cable', eq: 'cable', bp: 'chest', tg: 'pectorals' }];
  const customView = panelView(custom, binding, { session: beginSession(custom, 6, NOW) }, 6, NOW);
  assert.equal(customView.entries[0].muscles[2], 1);
  assert.ok(Math.abs(customView.entries[0].weightStep - 4.54) < 0.001);
  assert.deepEqual(snapshot(raw, 6, new Date(NOW), { enhanced: true }).entries[0].muscles, plan.entries[0].muscles);
});
