import { test } from 'node:test';
import assert from 'node:assert/strict';
import { beginSession, completedState, editRow, panelView } from '../sessions/model.mjs';
import { syncSideAggregate } from '../vendor/opengym/frontend/src/lib/workout-model.js';

const NOW = Date.parse('2026-10-23T05:40:00Z');
const binding = { slug: 'alpha', name: 'Alpha', uid: 'synthetic_alpha' };

function fixture(overrides = {}) {
  const state = {
    unit: 'kg', week: { 5: 'routine' }, dayPlan: {}, workouts: [],
    customEx: [], exNotes: {}, exWeights: {}, bodyweight: [],
    routines: [{
      id: 'routine', name: 'Synthetic workout',
      ex: [
        { id: '0334', sets: 3, reps: 15, weight: 6.8, prog: 'off', ...overrides },
        { id: '0043', sets: 2, reps: 8, weight: 20, prog: 'off' },
      ],
    }],
  };
  return { state, session: beginSession(state, 4, NOW) };
}

test('registering 5 kg and 12 reps replaces later targets without completing them', () => {
  const { state, session } = fixture();
  const originalState = structuredClone(state);
  const originalSession = structuredClone(session);
  const next = editRow(session, { exercise: 0, row: 0, done: true, weight: 5, reps: 12 });

  assert.deepEqual(next.active.entries[0].sets.map(row => [row.w, row.r, row.done]), [
    [5, 12, true], [5, 12, false], [5, 12, false],
  ]);
  assert.deepEqual(next.active.entries[1], session.active.entries[1]);
  assert.deepEqual(session, originalSession);
  assert.deepEqual(state, originalState);
  assert.equal(next.revision, session.revision + 1);

  const view = panelView(state, binding, { session: next, token: true }, 4, NOW);
  assert.deepEqual(view.entries[0].sets.map(row => [row.weight, row.reps, row.done]), [
    [5, 12, true], [5, 12, false], [5, 12, false],
  ]);
  const saved = completedState(state, next, NOW + 60000);
  assert.equal(saved.workout.entries[0].sets.filter(row => row.done).length, 1);
  assert.equal(saved.workout.vol, 60);
  assert.deepEqual(saved.state.routines, state.routines);
});

test('photo: registering work set 2 at 11.3 kg changes set 3 but not warmups or set 1', () => {
  const { state, session } = fixture({ warmupSets: 2, weight: 10.2, reps: 11 });
  const originalState = structuredClone(state);
  const entry = session.active.entries[0];
  entry.sets[2].done = true;
  const protectedRows = structuredClone(entry.sets.slice(0, 3));
  const next = editRow(session, { exercise: 0, row: 3, done: true, weight: 11.3, reps: 10 });

  assert.deepEqual(next.active.entries[0].sets.slice(0, 3), protectedRows);
  assert.deepEqual(next.active.entries[0].sets.slice(3).map(row => [row.w, row.r, row.done]), [
    [11.3, 10, true], [11.3, 10, false],
  ]);
  const view = panelView(state, binding, { session: next, token: true }, 4, NOW);
  assert.equal(view.entries[0].sets[4].weight, 11.3);
  assert.equal(view.entries[0].sets[4].done, false);
  assert.deepEqual(next.active.entries[1], session.active.entries[1]);
  assert.deepEqual(state, originalState);
});

test('only changed fields carry forward, including a new explicit zero load', () => {
  const { state, session } = fixture();
  session.active.entries[0].sets[1].r = 10;
  session.active.entries[0].sets[1].weightOrigin = 'manual';
  const next = editRow(session, { exercise: 0, row: 0, done: true, weight: 0, reps: 15 });
  assert.equal(next.active.entries[0].sets[1].w, 0);
  assert.equal(next.active.entries[0].sets[1].r, 10);
  assert.equal(next.active.entries[0].sets[1].weightOrigin, 'manual');
  assert.equal(next.active.entries[0].sets[2].r, 15);
  const view = panelView(state, binding, { session: next, token: true }, 4, NOW);
  assert.equal(view.entries[0].sets[1].weight, 0);
});

test('unchanged registration leaves deliberately different later targets alone', () => {
  const { session } = fixture();
  session.active.entries[0].sets[1].w = 8;
  session.active.entries[0].sets[1].r = 10;
  const later = structuredClone(session.active.entries[0].sets.slice(1));
  const next = editRow(session, { exercise: 0, row: 0, done: true, weight: 6.8, reps: 15 });
  assert.deepEqual(next.active.entries[0].sets.slice(1), later);
});

test('earlier results, later completed rows and all warmups remain untouched', () => {
  const { session } = fixture();
  const entry = session.active.entries[0];
  entry.sets = [
    { w: 4, r: 15, done: true },
    { w: 6.8, r: 15, done: false },
    { w: 8, r: 10, done: true },
    { w: 3, r: 8, phase: 'warmup', done: false },
    { w: 6.8, r: 15, done: false },
  ];
  const before = structuredClone(entry.sets);
  const next = editRow(session, { exercise: 0, row: 1, done: true, weight: 5, reps: 12 });
  for (const index of [0, 2, 3]) assert.deepEqual(next.active.entries[0].sets[index], before[index]);
  assert.deepEqual(next.active.entries[0].sets[4], {
    w: 5, r: 12, done: false, weightOrigin: 'manual',
  });
});

test('editing or registering a warmup never flattens the following prescriptions', () => {
  const { session } = fixture();
  session.active.entries[0].sets.unshift(
    { w: 2, r: 8, phase: 'warmup', done: false },
    { w: 4, r: 8, warmup: true, done: false },
  );
  const remaining = structuredClone(session.active.entries[0].sets.slice(1));
  const next = editRow(session, { exercise: 0, row: 0, done: true, weight: 3, reps: 10 });
  assert.deepEqual(next.active.entries[0].sets.slice(1), remaining);
});

test('native generated warmup ramps remain distinct from changed working sets', () => {
  const { session } = fixture({ warmupSets: 2, weight: 40, reps: 8 });
  const warmups = structuredClone(session.active.entries[0].sets.slice(0, 2));
  assert(warmups.every(row => row.phase === 'warmup'));
  const next = editRow(session, { exercise: 0, row: 2, done: true, weight: 35, reps: 7 });
  assert.deepEqual(next.active.entries[0].sets.slice(0, 2), warmups);
  assert.deepEqual(next.active.entries[0].sets.slice(2).map(row => [row.w, row.r, row.done]), [
    [35, 7, true], [35, 7, false], [35, 7, false],
  ]);
});

test('undo or an unregistered draft edit does not alter subsequent sets', () => {
  const { session } = fixture();
  session.active.entries[0].sets[0].done = true;
  const remaining = structuredClone(session.active.entries[0].sets.slice(1));
  const undone = editRow(session, { exercise: 0, row: 0, done: false, weight: 5, reps: 12 });
  assert.deepEqual(undone.active.entries[0].sets.slice(1), remaining);
  const draft = editRow(session, { exercise: 0, row: 1, weight: 7.3 });
  assert.deepEqual(draft.active.entries[0].sets[2], session.active.entries[0].sets[2]);
});

test('per-side forwarding protects completed limbs and never changes the opposite limb', () => {
  const { session } = fixture({ side: true, reps: 24 });
  const entry = session.active.entries[0];
  entry.sets[1].sides.R = { w: 8, r: 9, done: true };
  entry.sets[1] = syncSideAggregate(entry.sets[1]);
  entry.sets[2].sides.L = { w: 9, r: 11, done: true };
  entry.sets[2] = syncSideAggregate(entry.sets[2]);
  const before = structuredClone(entry.sets);

  const left = editRow(session, { exercise: 0, row: 0, side: 'L', done: true, weight: 7.3, reps: 10 });
  assert.deepEqual(left.active.entries[0].sets[0].sides.R, before[0].sides.R);
  assert.equal(left.active.entries[0].sets[0].done, false);
  assert.equal(left.active.entries[0].sets[1].sides.L.w, 7.3);
  assert.equal(left.active.entries[0].sets[1].sides.L.r, 10);
  assert.deepEqual(left.active.entries[0].sets[1].sides.R, before[1].sides.R);
  assert.deepEqual(left.active.entries[0].sets[2], before[2]);

  const both = editRow(left, { exercise: 0, row: 0, side: 'R', done: true, weight: 7.3, reps: 10 });
  assert.equal(both.active.entries[0].sets[0].done, true);
  assert.deepEqual(both.active.entries[0].sets[1].sides.R, before[1].sides.R);
  assert.deepEqual(both.active.entries[0].sets[2].sides.L, before[2].sides.L);
  assert.equal(both.active.entries[0].sets[2].sides.R.w, 7.3);
  assert.equal(both.active.entries[0].sets[2].sides.R.done, false);
  assert.equal(both.active.entries[0].sets[2].r, 21);
  assert.equal(both.active.entries[0].sets[2].done, false);
});

test('timed work reuses changed duration without rewriting original plan stamps', () => {
  const { session } = fixture({ mode: 'time', sec: 30, weight: 0 });
  const next = editRow(session, { exercise: 0, row: 0, done: true, weight: 0, seconds: 45 });
  assert.deepEqual(next.active.entries[0].sets.map(row => [row.sec, row.done]), [
    [45, true], [45, false], [45, false],
  ]);
  assert.equal(next.active.entries[0].target.sec, 30);
});

test('cardio uses changed minutes and speed only as pending targets', () => {
  const { session } = fixture({ mode: 'cardio', min: 10, speed: 5 });
  const next = editRow(session, {
    exercise: 0, row: 0, done: true, minutes: 8.5, speed: 7.4,
  });
  assert.deepEqual(next.active.entries[0].sets.map(row => [row.min, row.speed, row.done]), [
    [8.5, 7.4, true], [8.5, 7.4, false], [8.5, 7.4, false],
  ]);
});

test('rejected values cannot partially change any later values', () => {
  const { session } = fixture();
  const before = structuredClone(session);
  for (const change of [{ weight: NaN }, { reps: -1 }, { weight: 5, reps: 2.5 }, { seconds: 45 }]) {
    assert.throws(() => editRow(session, { exercise: 0, row: 0, done: true, ...change }), /invalid_value/);
    assert.deepEqual(session, before);
  }
});
