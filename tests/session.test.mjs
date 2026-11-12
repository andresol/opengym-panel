import { test } from 'node:test';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { PanelError, beginSession, completedState, editRow, panelView } from '../sessions/model.mjs';
import { SessionService } from '../sessions/service.mjs';
import { makeSessionServer } from '../sessions/server.mjs';

const NOW = Date.parse('2026-10-20T14:00:00Z');
const fixture = (name = 'Routine', weight = 20) => ({
  unit: 'kg', week: { 2: 'r1' }, dayPlan: {}, workouts: [], customEx: [], exNotes: {}, exWeights: {},
  routines: [{ id: 'r1', name, ex: [{ id: '0043', sets: 2, reps: 8, weight, prog: 'off', restSec: 90 }] }],
  bodyweight: [], _rev: 0, _ts: NOW - 1000,
});
const binding = { slug: 'alpha', name: 'Alpha', uid: 'profilealpha' };
const request = (action, extra = {}) => ({ action, requestId: crypto.randomUUID(), ...extra });
const sessionRequest = (action, session, extra = {}) => request(action, {
  sessionId: session.active.id, revision: session.revision, ...extra,
});

class MockApi {
  constructor() { this.states = new Map(); this.writes = []; this.conflict = false; this.failAfterWrite = false; }
  async identity(token) {
    if (!this.states.has(token)) throw new Error('Unrecognised fixture token');
    return { id: token, admin: false };
  }
  async redeem(code) { return { token: code === 'ABCDEFGH' ? binding.uid : 'profilebeta', user: { id: code === 'ABCDEFGH' ? binding.uid : 'profilebeta', admin: false } }; }
  async state(token) { const state = structuredClone(this.states.get(token)); return { state, rev: state._rev }; }
  async save(token, state, baseRev) {
    const current = this.states.get(token);
    if (this.conflict) {
      this.conflict = false;
      current.workouts.push({ id: 'phone-workout', d: '2026-10-20', entries: [] });
      current.week[3] = 'r1'; current._rev++;
      return false;
    }
    assert.equal(baseRev, current._rev);
    const next = structuredClone(state); next._rev++;
    this.states.set(token, next); this.writes.push({ token, state: next });
    if (this.failAfterWrite) { this.failAfterWrite = false; throw new Error('Lost fixture response'); }
    return true;
  }
}

function harness() {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'gym-sessions-'));
  const dataDir = path.join(directory, 'data'), storeDir = path.join(directory, 'drafts');
  fs.mkdirSync(dataDir);
  const api = new MockApi();
  const profiles = [binding, { slug: 'beta', name: 'Beta', uid: 'profilebeta' }];
  for (const [index, profile] of profiles.entries()) {
    const data = fixture(profile.name, index ? 5 : 20);
    fs.writeFileSync(path.join(dataDir, `state-${profile.uid}.json`), JSON.stringify(data));
    api.states.set(profile.uid, structuredClone(data));
  }
  const service = new SessionService({ profiles, dataDir, storeDir, api, now: () => NOW });
  return { directory, dataDir, storeDir, api, profiles, service };
}

async function pairedStarted(h) {
  await h.service.enqueue('alpha', request('pair', { code: 'ABCDEFGH' }));
  await h.service.enqueue('alpha', request('start', { day: 1 }));
  return h.service.record('alpha').session;
}

test('start builds native prescriptions without completing rows or mutating source', () => {
  const state = fixture(), before = JSON.stringify(state);
  const session = beginSession(state, 1, NOW);
  assert.equal(session.active.entries.length, 1);
  assert(session.active.entries[0].sets.every(row => row.done === false));
  assert.equal(JSON.stringify(state), before);
  assert.throws(() => beginSession(state, 0, NOW), /no_planned_workout/);
  const view = panelView(state, binding, { session, token: 'never-show-token' }, 1, NOW);
  assert.equal(view.profile, 'Alpha'); assert.equal(view.entries[0].name, 'Stangknebøy');
  assert(!JSON.stringify(view).includes(binding.uid)); assert(!JSON.stringify(view).includes('never-show-token'));
});

test('only an explicitly completed row enters the finished workout', () => {
  const state = fixture();
  let session = beginSession(state, 1, NOW);
  session = editRow(session, { exercise: 0, row: 0, done: true, weight: 17.5, reps: 7 });
  const result = completedState(state, session, NOW + 60000);
  assert.equal(result.workout.entries.length, 1);
  assert.equal(result.workout.entries[0].sets.filter(row => row.done).length, 1);
  assert.equal(result.workout.entries[0].sets[0].w, 17.5);
  assert.equal(result.workout.entries[0].sets[0].r, 7);
  assert.equal(state.workouts.length, 0); assert.equal(result.state.workouts.length, 1);
  assert.deepEqual(result.state.routines, state.routines);
  assert.throws(() => editRow(session, { exercise: 0, row: 0, done: true, reps: -1 }), /invalid_value/);
  assert.throws(() => editRow(session, { exercise: 1, row: 0, done: true }), /invalid_set/);
});

test('rest-day choice previews only own routines and never changes the weekly plan', () => {
  const state = fixture('Own template'), before = JSON.stringify(state);
  const empty = panelView(state, binding, null, 0, NOW);
  assert.equal(empty.state, 'rest');
  const choice = empty.routineChoices[0];
  assert.match(choice.key, /^[a-f0-9]{24}$/);
  assert.equal(choice.name, 'Own template');
  const preview = panelView(state, binding, null, 0, NOW, choice.key);
  assert.equal(preview.entries.length, 1);
  assert.equal(preview.title, 'Own template');
  assert.equal(preview.routineSelection, choice.key);
  assert.deepEqual(preview.week, empty.week);
  assert.equal(JSON.stringify(state), before);
  const beta = panelView(state, { ...binding, uid: 'profilebeta' }, null, 0, NOW);
  assert.notEqual(beta.routineChoices[0].key, choice.key);
  assert.throws(() => panelView(state, binding, null, 0, NOW, beta.routineChoices[0].key), /routine_unavailable/);
  assert.throws(() => panelView(state, binding, null, 1, NOW, choice.key), /not_rest_day/);
  assert.throws(() => panelView(state, binding, null, 0, NOW, 'r1'), /invalid_routine/);
  const wire = JSON.stringify(preview);
  assert(!wire.includes(binding.uid)); assert(!wire.includes('"r1"'));
  const removed = structuredClone(state); removed.routines = [];
  assert.throws(() => panelView(removed, binding, null, 0, NOW, choice.key), /routine_unavailable/);
  const noRoutines = panelView(removed, binding, null, 0, NOW);
  assert.deepEqual(noRoutines.routineChoices, []);
});

test('selected rest-day routine pairs, starts, resumes and saves 7.3 kg without rescheduling', async () => {
  const h = harness();
  const today = Date.parse('2026-10-21T14:00:00Z');
  h.service.now = () => today;
  const before = structuredClone(h.api.states.get(binding.uid));
  const betaFile = fs.readFileSync(path.join(h.dataDir, 'state-profilebeta.json'), 'utf8');
  try {
    const choice = h.service.view('alpha').routineChoices[0];
    const paired = await h.service.enqueue('alpha', request('pair', { code: 'ABCDEFGH', day: 2, routine: choice.key }));
    assert.equal(paired.routineSelection, choice.key);
    assert.equal(h.api.writes.length, 0);
    await h.service.enqueue('alpha', request('start', { day: 2, routine: choice.key }));
    let session = h.service.record('alpha').session;
    assert.equal(session.active.d, '2026-10-21');
    assert.deepEqual(session.active.routineIds, ['r1']);
    const restored = new SessionService({ profiles: h.profiles, dataDir: h.dataDir, storeDir: h.storeDir, api: h.api, now: () => today });
    const active = restored.view('alpha');
    assert.equal(active.session.id, session.active.id);
    assert.equal(active.routineSelection, null); assert.deepEqual(active.routineChoices, []);
    // Starting again, even with a stale choice, must preserve the existing draft.
    await h.service.enqueue('alpha', request('start', { day: 2, routine: 'f'.repeat(24) }));
    assert.equal(h.service.record('alpha').session.active.id, session.active.id);
    await h.service.enqueue('alpha', sessionRequest('set', session, { exercise: 0, row: 0, done: true, weight: 7.3, reps: 8 }));
    session = h.service.record('alpha').session;
    assert.equal(h.service.view('alpha').entries[0].sets[0].weight, 7.3);
    await h.service.enqueue('alpha', sessionRequest('finish', session));
    const saved = h.api.states.get(binding.uid);
    assert.equal(saved.workouts[0].entries[0].sets[0].w, 7.3);
    assert.equal(saved.workouts[0].d, '2026-10-21');
    assert.deepEqual(saved.week, before.week); assert.deepEqual(saved.dayPlan, before.dayPlan);
    assert.deepEqual(saved.routines, before.routines);
    assert.equal(h.api.states.get('profilebeta').workouts.length, 0);
    assert.equal(fs.readFileSync(path.join(h.dataDir, 'state-profilebeta.json'), 'utf8'), betaFile);
    assert.equal(h.service.view('alpha').state, 'rest');
  } finally { fs.rmSync(h.directory, { recursive: true, force: true }); }
});

test('start revalidates a removed/foreign choice against fresh own-profile state', async () => {
  const h = harness();
  try {
    await h.service.enqueue('alpha', request('pair', { code: 'ABCDEFGH' }));
    const other = h.service.view('beta', 0).routineChoices[0].key;
    await assert.rejects(h.service.enqueue('alpha', request('start', { day: 0, routine: other })), /routine_unavailable/);
    const own = h.service.view('alpha', 0).routineChoices[0].key;
    h.api.states.get(binding.uid).routines = [];
    await assert.rejects(h.service.enqueue('alpha', request('start', { day: 0, routine: own })), /routine_unavailable/);
    assert.equal(h.service.record('alpha').session, undefined);
    assert.equal(h.api.writes.length, 0);
  } finally { fs.rmSync(h.directory, { recursive: true, force: true }); }
});

test('per-side rows retain independent results and partial completion', () => {
  const state = fixture(); state.routines[0].ex[0].side = true;
  let session = beginSession(state, 1, NOW);
  const row = session.active.entries[0].sets[0]; assert(row.sides);
  session = editRow(session, { exercise: 0, row: 0, side: 'L', done: true, weight: 10, reps: 5 });
  assert.equal(session.active.entries[0].sets[0].done, false);
  const result = completedState(state, session, NOW + 60000);
  assert.equal(result.workout.entries[0].sets[0].sides.L.done, true);
  assert.equal(result.workout.entries[0].sets[0].sides.R.done, false);
  assert.throws(() => editRow(session, { exercise: 0, row: 0, done: true }), /invalid_side/);
});

test('pairing cannot cross profiles; starting/editing/discarding writes no OpenGym data', async () => {
  const h = harness();
  try {
    await assert.rejects(h.service.enqueue('alpha', request('pair', { code: 'BCDEFGHJ' })), /wrong_profile/);
    assert.equal(h.service.record('alpha').token, undefined);
    let session = await pairedStarted(h);
    const command = sessionRequest('set', session, { exercise: 0, row: 0, done: true });
    await h.service.enqueue('alpha', command);
    session = h.service.record('alpha').session;
    await h.service.enqueue('alpha', command); // Lost acknowledgement does not double-apply.
    assert.equal(h.service.record('alpha').session.revision, session.revision);
    await h.service.enqueue('alpha', sessionRequest('discard', session));
    assert.equal(h.api.writes.length, 0);
    assert.equal(h.service.record('alpha').session, undefined);
    assert.equal(h.service.record('beta').session, undefined);
  } finally { fs.rmSync(h.directory, { recursive: true, force: true }); }
});

test('draft survives restart and rejects a stale session revision', async () => {
  const h = harness();
  try {
    const session = await pairedStarted(h);
    await h.service.enqueue('alpha', sessionRequest('set', session, { exercise: 0, row: 0, done: true }));
    const reloaded = new SessionService({ profiles: h.profiles, dataDir: h.dataDir, storeDir: h.storeDir, api: h.api, now: () => NOW });
    assert.equal(reloaded.record('alpha').session.active.entries[0].sets[0].done, true);
    await assert.rejects(reloaded.enqueue('alpha', sessionRequest('set', session, { exercise: 0, row: 1, done: true })), /session_changed/);
    assert.equal(h.api.writes.length, 0);
    assert.equal(fs.statSync(path.join(h.storeDir, 'alpha.json')).mode & 0o777, 0o600);
  } finally { fs.rmSync(h.directory, { recursive: true, force: true }); }
});

test('forwarded values persist once across restart/retry without source or profile writes', async () => {
  const h = harness();
  try {
    const original = structuredClone(h.api.states.get(binding.uid));
    const betaFile = fs.readFileSync(path.join(h.dataDir, 'state-profilebeta.json'), 'utf8');
    const session = await pairedStarted(h);
    const command = sessionRequest('set', session, {
      exercise: 0, row: 0, done: true, weight: 7.3, reps: 6,
    });
    await h.service.enqueue('alpha', command);
    const changed = h.service.record('alpha').session;
    assert.equal(changed.revision, session.revision + 1);
    assert.equal(changed.active.entries[0].sets[1].w, 7.3);
    assert.equal(changed.active.entries[0].sets[1].r, 6);
    assert.equal(changed.active.entries[0].sets[1].done, false);
    assert.equal(h.api.writes.length, 0);
    assert.deepEqual(h.api.states.get(binding.uid), original);
    assert.equal(h.service.record('beta').session, undefined);

    const restored = new SessionService({
      profiles: h.profiles, dataDir: h.dataDir, storeDir: h.storeDir,
      api: h.api, now: () => NOW,
    });
    assert.equal(restored.view('alpha').entries[0].sets[1].weight, 7.3);
    await restored.enqueue('alpha', sessionRequest('set', changed, {
      exercise: 0, row: 1, done: false, weight: 8.1,
    }));
    const pending = restored.record('alpha').session;
    await restored.enqueue('alpha', command);
    assert.deepEqual(restored.record('alpha').session, pending);
    await assert.rejects(restored.enqueue('alpha', sessionRequest('set', session, {
      exercise: 0, row: 0, done: true, weight: 9,
    })), /session_changed/);
    assert.deepEqual(restored.record('alpha').session, pending);

    await restored.enqueue('alpha', sessionRequest('finish', pending));
    const saved = h.api.states.get(binding.uid);
    assert.equal(saved.workouts.length, 1);
    assert.equal(saved.workouts[0].entries[0].sets.filter(row => row.done).length, 1);
    assert.equal(saved.workouts[0].vol, 7.3 * 6);
    assert.deepEqual(saved.routines, original.routines);
    assert.equal(fs.readFileSync(path.join(h.dataDir, 'state-profilebeta.json'), 'utf8'), betaFile);
    assert.equal(h.api.states.get('profilebeta').workouts.length, 0);
  } finally {
    fs.rmSync(h.directory, { recursive: true, force: true });
  }
});

test('finish preserves phone changes after CAS conflict and verifies one saved workout', async () => {
  const h = harness();
  try {
    let session = await pairedStarted(h);
    await h.service.enqueue('alpha', sessionRequest('set', session, { exercise: 0, row: 0, done: true }));
    session = h.service.record('alpha').session; h.api.conflict = true;
    await h.service.enqueue('alpha', sessionRequest('finish', session));
    const saved = h.api.states.get(binding.uid);
    assert.equal(saved.workouts.length, 2); assert.equal(saved.workouts[0].id, 'phone-workout');
    assert.equal(saved.week[3], 'r1'); assert.equal(h.api.writes.length, 1);
    assert.equal(h.service.record('alpha').lastResult.state, 'saved');
    assert.equal(h.api.states.get('profilebeta').workouts.length, 0);
    assert(fs.readdirSync(path.join(h.storeDir, 'backups', 'alpha')).length > 0);
  } finally { fs.rmSync(h.directory, { recursive: true, force: true }); }
});

test('lost API acknowledgement is recovered without a duplicate workout', async () => {
  const h = harness();
  try {
    let session = await pairedStarted(h);
    await h.service.enqueue('alpha', sessionRequest('set', session, { exercise: 0, row: 0, done: true }));
    session = h.service.record('alpha').session; h.api.failAfterWrite = true;
    await assert.rejects(h.service.enqueue('alpha', sessionRequest('finish', session)), /Lost fixture response/);
    assert.equal(h.service.record('alpha').session.phase, 'saving');
    await h.service.enqueue('alpha', sessionRequest('finish', session));
    assert.equal(h.api.states.get(binding.uid).workouts.length, 1);
    assert.equal(h.api.writes.length, 1); assert.equal(h.service.record('alpha').session, undefined);
  } finally { fs.rmSync(h.directory, { recursive: true, force: true }); }
});

test('empty session closes without recording a fictitious workout', async () => {
  const h = harness();
  try {
    const session = await pairedStarted(h);
    await h.service.enqueue('alpha', sessionRequest('finish', session));
    assert.equal(h.api.writes.length, 0); assert.equal(h.api.states.get(binding.uid).workouts.length, 0);
    assert.equal(h.service.record('alpha').lastResult.state, 'closed');
  } finally { fs.rmSync(h.directory, { recursive: true, force: true }); }
});

test('read token cannot write; routes never accept UID or another profile body binding', async () => {
  const h = harness(), readToken = 'r'.repeat(40), writeToken = 'w'.repeat(40);
  const server = makeSessionServer({ service: h.service, readToken, writeToken });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const get = (route, token = readToken) => fetch(base + route, { headers: { Authorization: `Bearer ${token}` } });
  try {
    assert.equal((await get('/api/profiles')).status, 200);
    assert.equal((await get('/api/profiles/alpha/plan?uid=profilebeta')).status, 400);
    assert.equal((await get('/api/profiles/alpha/plan?day=1&day=2')).status, 400);
    const response = await fetch(base + '/api/profiles/alpha/action', {
      method: 'POST', headers: { Authorization: `Bearer ${readToken}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(request('start', { day: 1 })),
    });
    assert.equal(response.status, 401); assert.equal(h.api.writes.length, 0);
    assert.equal((await get('/config.json')).status, 404);
  } finally {
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
    fs.rmSync(h.directory, { recursive: true, force: true });
  }
});

test('time, cardio and unit conversions retain actual results, not fake measurements', () => {
  const timed = fixture(); timed.routines[0].ex[0] = { id: '0043', sets: 1, mode: 'time', secs: 30, sec: 30, seconds: 30, weight: 4, prog: 'off' };
  let session = beginSession(timed, 1, NOW);
  assert.equal(panelView(timed, binding, { session }, 1, NOW).entries[0].mode, 'time');
  session = editRow(session, { exercise: 0, row: 0, seconds: 45, weight: 3.5, done: true });
  assert.equal(completedState(timed, session, NOW + 60000).workout.entries[0].sets[0].sec, 45);
  assert.equal(session.active.bw, null);
  const pounds = { ...timed, unit: 'lb' };
  const converted = completedState(pounds, session, NOW + 60000).workout.entries[0].sets[0];
  assert(converted.w > 7 && converted.w < 8);
  const cardio = fixture(); cardio.routines[0].ex[0] = { id: '0043', sets: 1, mode: 'cardio', min: 20, speed: 8, prog: 'off' };
  let running = beginSession(cardio, 1, NOW);
  running = editRow(running, { exercise: 0, row: 0, minutes: 12.5, speed: 7.4, done: true });
  const logged = completedState(cardio, running, NOW + 750000).workout.entries[0].sets[0];
  assert.equal(logged.min, 12.5); assert.equal(logged.speed, 7.4);
  assert.throws(() => editRow(running, { exercise: 0, row: 0, reps: 5 }), /invalid_value/);
});

test('positive HTTP workflow uses separate write key and sanitized account binding', async () => {
  const h = harness(), readToken = 'r'.repeat(40), writeToken = 'w'.repeat(40);
  const server = makeSessionServer({ service: h.service, readToken, writeToken });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const send = async command => {
    const response = await fetch(base + '/api/profiles/alpha/action', { method: 'POST',
      headers: { Authorization: `Bearer ${writeToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify(command) });
    return { status: response.status, view: await response.json() };
  };
  try {
    assert.equal((await send(request('start', { day: 1 }))).status, 401);
    const readPlan = route => fetch(base + '/api/profiles/alpha/plan' + route,
      { headers: { Authorization: `Bearer ${readToken}` } });
    const rest = await (await readPlan('?day=0')).json();
    const key = rest.routineChoices[0].key;
    const preview = await readPlan('?day=0&routine=' + key);
    assert.equal(preview.status, 200);
    assert.equal((await preview.json()).routineSelection, key);
    assert.equal((await readPlan('?routine=raw-id')).status, 400);
    assert.equal((await readPlan('?day=0&routine=' + key + '&routine=' + key)).status, 400);
    const foreign = h.service.view('beta', 0).routineChoices[0].key;
    assert.equal((await readPlan('?day=0&routine=' + foreign)).status, 409);
    assert.equal((await send(request('pair', { code: 'ABCDEFGH' }))).status, 200);
    const started = await send(request('start', { day: 1 })); assert.equal(started.status, 200);
    const active = started.view.session;
    const changed = await send(request('set', { sessionId: active.id, revision: active.revision, exercise: 0, row: 0, done: true, weight: 15.5, reps: 6 }));
    assert.equal(changed.view.session.done, 1);
    assert(!JSON.stringify(changed.view).includes(binding.uid));
    const saved = await send(request('finish', { sessionId: active.id, revision: changed.view.session.revision }));
    assert.equal(saved.status, 200); assert.equal(saved.view.lastResult.state, 'saved');
    assert.equal(h.api.states.get(binding.uid).workouts[0].entries[0].sets[0].w, 15.5);
    assert.equal(h.api.states.get('profilebeta').workouts.length, 0);
  } finally {
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
    fs.rmSync(h.directory, { recursive: true, force: true });
  }
});

test('revoked auth preserves explicit saving draft and pairing resumes without extra history', async () => {
  const h = harness();
  try {
    let session = await pairedStarted(h);
    await h.service.enqueue('alpha', sessionRequest('set', session, { exercise: 0, row: 0, done: true }));
    session = h.service.record('alpha').session;
    const identity = h.api.identity.bind(h.api);
    h.api.identity = async () => { throw new PanelError('pair_required', 401); };
    await assert.rejects(h.service.enqueue('alpha', sessionRequest('finish', session)), /pair_required/);
    assert.equal(h.service.record('alpha').token, undefined);
    assert.equal(h.service.record('alpha').session.phase, 'saving');
    assert.equal(h.api.writes.length, 0);
    h.api.identity = identity;
    await h.service.enqueue('alpha', request('pair', { code: 'ABCDEFGH' }));
    await h.service.retrySaving();
    assert.equal(h.api.writes.length, 1); assert.equal(h.service.record('alpha').lastResult.state, 'saved');
  } finally { fs.rmSync(h.directory, { recursive: true, force: true }); }
});
