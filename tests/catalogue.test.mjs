import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { EXDB, CATALOGUE, EXIDX } from '../vendor/opengym/frontend/src/lib/exercises.js';
import { beginSession, panelView } from '../sessions/model.mjs';
import { snapshot } from '../bridge/model.mjs';

const manifest = JSON.parse(fs.readFileSync(new URL('../native/catalogue-modern.json', import.meta.url)));

test('complete 1.4.4 catalogue and all firmware media aliases match the pinned source', () => {
  assert.equal(EXDB.length, 5632);
  assert.equal(CATALOGUE.length, 5632);
  assert.equal(new Set(CATALOGUE.map(row => row.id)).size, 5632);
  assert.equal(manifest.total_count, CATALOGUE.length);
  for (const old of EXDB) {
    assert.equal(EXIDX[old.id].n, old.n);
    assert.equal(EXIDX[old.id].img, old.img);
    assert.equal(EXIDX[old.id].gif, old.gif);
  }
  assert.equal(manifest.source_version, '1.4.4');
  for (const row of CATALOGUE) {
    assert.equal(EXIDX[row.id].eq, row.eq);
    assert.match(manifest.files[`img/v140-${row.id}.jpg`], /^still\/[0-9]+\.webp$/);
    assert.match(manifest.files[`gif/v140-${row.id}.gif`], /^clip\/[0-9]+\.mp4$/);
  }
});

test('new loaded and bodyweight exercises project through the installed panel contract', () => {
  const now = Date.parse('2026-10-27T12:00:00Z');
  const ids = ['1060', '1202', '1547', '9698', '2656', '1581'];
  const state = {
    unit: 'kg', week: { 2: 'synthetic' }, dayPlan: {}, workouts: [], customEx: [],
    exNotes: {}, exWeights: {}, bodyweight: [],
    routines: [{ id: 'synthetic', name: 'Offline catalogue test',
      ex: ids.map(id => ({ id, sets: 2, reps: 12, weight: 0, prog: 'off' })) }],
  };
  const before = structuredClone(state);
  const binding = { slug: 'synthetic', uid: 'offline-only', name: 'Synthetic' };
  const plan = snapshot(state, 1, new Date(now), { enhanced: true });
  const session = beginSession(state, 1, now);
  const active = panelView(state, binding, { session, token: true }, 1, now);
  for (const view of [plan, active]) {
    assert.equal(view.entries.length, ids.length);
    for (const [index, row] of view.entries.entries()) {
      assert.equal(row.name, EXIDX[ids[index]].n);
      assert.match(row.image, /^\/media\/img\/v140-[0-9]+\.jpg$/);
      assert.match(row.animation, /^\/media\/gif\/v140-[0-9]+\.gif$/);
      assert.equal(row.bodyweight, index === 5);
    }
  }
  assert.deepEqual(state, before);
  assert.equal(state.workouts.length, 0);
});
