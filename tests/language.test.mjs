import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';

const cwd = fileURLToPath(new URL('..', import.meta.url));

function project(language) {
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', `
    import { beginSession, panelView, editRow, completedState } from './sessions/model.mjs';
    const now = Date.parse('2026-10-20T14:00:00Z');
    const binding = { slug: 'demo', name: 'Sam', uid: 'synthetic-only' };
    const raw = {
      unit: 'kg', week: { 2: 'r1' }, workouts: [], customEx: [{ id: 'mine', n: 'Min egen øvelse', bp: 'upper legs', eq: 'barbell' }], exNotes: {},
      routines: [{ id: 'r1', name: 'Min egen økt', ex: [
        { id: '0043', sets: 2, reps: 8, weight: 0, restSec: 90, note: 'Min norske merknad', prog: 'off' },
        { id: 'mine', sets: 1, reps: 6, weight: 10, prog: 'off' },
      ] }],
    };
    const before = JSON.stringify(raw);
    const preview = panelView(raw, binding, null, 1, now);
    const rest = panelView(raw, binding, null, 0, now);
    const session = beginSession(raw, 1, now);
    const active = panelView(raw, binding, { session, token: 'synthetic' }, 1, now);
    const edited = editRow(session, { exercise: 0, row: 0, done: true, reps: 7, weight: 12.5 }, now);
    const saved = completedState(raw, edited, now + 60000);
    console.log(JSON.stringify({ preview, rest, active,
      originalUnchanged: before === JSON.stringify(raw),
      savedName: saved.workout.name,
      savedSets: saved.workout.entries[0].sets,
      savedRoutines: saved.state.routines,
    }));
  `], {
    cwd, encoding: 'utf8',
    env: { ...process.env, PANEL_LANGUAGE: language, PANEL_TIMEZONE: 'Europe/Oslo' },
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test('English localizes planned, active and rest views without changing user text or workout semantics', () => {
  const nb = project('nb');
  const en = project('en');
  assert.equal(nb.preview.entries[0].name, 'Stangknebøy');
  assert.match(en.preview.entries[0].name, /squat/i);
  assert.equal(en.preview.language, 'en');
  assert.equal(en.preview.entries[0].load, 'Choose weight');
  assert.equal(en.preview.entries[0].detail, 'Rest 90 sec');
  assert.equal(en.active.entries[0].detail, 'Rest 90 sec');
  assert.equal(en.rest.title, 'Rest day');
  assert.equal(nb.rest.title, 'Hviledag');
  for (const view of [en.preview, en.active]) {
    assert.equal(view.profile, 'Sam');
    assert.equal(view.title, 'Min egen økt');
    assert.equal(view.entries[0].note, 'Min norske merknad');
    assert.equal(view.entries[1].name, 'Min egen øvelse');
  }
  assert(en.originalUnchanged && nb.originalUnchanged);
  assert.deepEqual(en.preview.entries[0].sets, nb.preview.entries[0].sets);
  assert.deepEqual(en.savedSets, nb.savedSets);
  assert.deepEqual(en.savedRoutines, nb.savedRoutines);
  assert.equal(en.savedName, 'Min egen økt');
});


test('unset backend language matches edition firmware default; explicit Norwegian remains available', () => {
  const defaults = JSON.parse(readFileSync(new URL('../firmware/config/installation.defaults.json', import.meta.url)));
  const env = { ...process.env };
  delete env.PANEL_LANGUAGE;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e',
    "import { LANGUAGE } from './bridge/language.mjs'; console.log(LANGUAGE);"],
    { cwd, env, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout.trim(), defaults.substitutions.panel_language);
  assert.equal(project('nb').preview.language, 'nb');
});
