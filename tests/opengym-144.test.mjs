import { test } from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { beginSession, completedState, editRow, panelView } from '../sessions/model.mjs';
import { snapshot } from '../bridge/model.mjs';
import { startProgramme } from '../vendor/opengym/frontend/src/lib/programmes.js';

const NOW = Date.parse('2026-11-09T12:00:00Z');
const binding = { slug: 'synthetic', name: 'Synthetic', uid: 'synthetic-only' };
const fixture = (id = '0025') => ({
  unit: 'kg', weekStart: 1, week: { 1: 'r' }, dayPlan: {}, workouts: [],
  customEx: [], exNotes: {}, exWeights: {}, bodyweight: [],
  routines: [{ id: 'r', name: 'Synthetic', ex: [{ id, sets: 2, reps: 10, weight: 20, prog: 'off' }] }],
});

test('all pinned 1.4.4 runtime modules and metadata are byte-identical to upstream', () => {
  const root = fileURLToPath(new URL('../', import.meta.url));
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'docs/upstream-1.4.4-sha256.json')));
  assert.equal(manifest.version, '1.4.4');
  assert.equal(manifest.commit, '5f5832db56080837b58342ff50f78631dcc63e07');
  assert(Object.keys(manifest.files).length >= 230);
  for (const [name, expected] of Object.entries(manifest.files)) {
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root, name))).digest('hex'), expected, name);
  }
});

test('1.4.4 per-bell meaning affects volume, while history and source remain untouched', () => {
  const state = fixture('0314');
  state.routines[0].ex[0].dbLoad = 'each';
  const before = structuredClone(state);
  let session = beginSession(state, 0, NOW);
  session = editRow(session, { exercise: 0, row: 0, done: true }, NOW + 1000);
  assert.equal(panelView(state, binding, { session }, 0, NOW).session.volume, 400);
  const result = completedState(state, session, NOW + 60000);
  assert.equal(result.workout.entries[0].target.dbLoad, 'each');
  assert.equal(result.workout.vol, 400);
  assert.deepEqual(state, before);
});

test('selected gym inventory is used without migrating source; saved workout keeps the gym', () => {
  const state = fixture('0314');
  state.equipProfiles = [{ id: 'home', name: 'Home', dumbbells: { kg: { weights: [5, 10], _ts: 1 } } },
    { id: 'other', name: 'Other', dumbbells: { kg: { weights: [12, 16], _ts: 2 } } }];
  state.activeEquipId = 'other';
  state.invGym = 'home';
  state.dumbbells = { kg: { weights: [5, 10], _ts: 1 } };
  const before = structuredClone(state);
  let session = beginSession(state, 0, NOW);
  assert.deepEqual(session.active.gym, { id: 'other', name: 'Other' });
  session = editRow(session, { exercise: 0, row: 0, done: true }, NOW + 1000);
  assert.deepEqual(completedState(state, session, NOW + 60000).workout.gym, session.active.gym);
  assert.deepEqual(state, before);
});

test('programme deload follows selected plan date and persists progression exclusion', () => {
  const state = fixture();
  state.programmes = { p: { id: 'p', name: 'Synthetic block', at: 1, days: { 1: ['r'] },
    weeks: [{}, { deload: true }] } };
  assert(startProgramme(state, 'p', '2026-11-02', NOW));
  const before = structuredClone(state);
  let session = beginSession(state, 0, NOW);
  assert.equal(session.active.entries[0].noProg, true);
  session = editRow(session, { exercise: 0, row: 0, done: true }, NOW + 1000);
  assert.equal(completedState(state, session, NOW + 60000).workout.excludeFromProgression, true);
  assert.deepEqual(state, before);
});

test('newly confirmed work has a stable tick time; undo clears it and no duplicate changes it', () => {
  let session = beginSession(fixture(), 0, NOW);
  session = editRow(session, { exercise: 0, row: 0, done: true }, NOW + 1000);
  assert.equal(session.active.entries[0].sets[0].at, NOW + 1000);
  session = editRow(session, { exercise: 0, row: 0, done: true }, NOW + 2000);
  assert.equal(session.active.entries[0].sets[0].at, NOW + 1000);
  session = editRow(session, { exercise: 0, row: 0, done: false }, NOW + 3000);
  assert.equal(session.active.entries[0].sets[0].at, undefined);
});

test('catalogue drawing aliases keep canonical public media without accepting custom URLs', () => {
  const view = snapshot(fixture('1019'), 0, new Date(NOW), { enhanced: true });
  assert.equal(view.entries[0].image, '/media/img/v140-3841.jpg');
  assert.equal(view.entries[0].animation, '/media/gif/v140-3841.gif');
});
