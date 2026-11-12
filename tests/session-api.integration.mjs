/** Manual integration against an isolated copy of the installed API image only.
 * The runner must supply /data containing ONLY the synthetic Alpha/Beta accounts.
 * Never run this against production OpenGym or a real account. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import { SessionService, OpenGymApi } from '../sessions/service.mjs';
if (process.env.GYM_SYNTHETIC_API !== 'isolated-network-none') throw new Error('Isolated runner required');
const db = JSON.parse(fs.readFileSync('/data/db.json'));
assert.deepEqual(db.users.map(user => user.id).sort(), ['fixture_alpha', 'fixture_beta']);
const secret = fs.readFileSync('/data/secret', 'utf8').trim();
const api = new OpenGymApi('http://127.0.0.1:3000');
function seedToken(uid) {
  const payload = `${uid}:${Date.now() + 86400000}:0`;
  return payload + '.' + crypto.createHmac('sha256', secret).update(payload).digest('base64url');
}
const profiles = [{ slug: 'alpha', name: 'Alpha', uid: 'fixture_alpha' }, { slug: 'beta', name: 'Beta', uid: 'fixture_beta' }];
const service = new SessionService({ profiles, dataDir: '/data', storeDir: '/drafts', api });
const command = (action, extra = {}) => ({ action, requestId: crypto.randomUUID(), ...extra });
let checks = 0;
for (const profile of profiles) {
  const auth = seedToken(profile.uid);
  assert.equal((await api.identity(auth)).id, profile.uid); checks++;
  const code = await api.request('/api/pair/create', auth, 'POST', {});
  assert.equal(code.status, 200);
  const paired = await service.enqueue(profile.slug, command('pair', { code: code.data.code }));
  assert(paired.paired); assert(!JSON.stringify(paired).includes(profile.uid)); checks++;
  await service.enqueue(profile.slug, command('start', { day: 1 }));
  let session = service.record(profile.slug).session;
  assert.equal((await api.state(auth)).state.workouts.length, 0); checks++;
  await service.enqueue(profile.slug, command('set', { sessionId: session.active.id, revision: session.revision,
    exercise: 0, row: 0, weight: profile.slug === 'alpha' ? 12.5 : 5, reps: 6, done: true }));
  session = service.record(profile.slug).session;
  const finish = command('finish', { sessionId: session.active.id, revision: session.revision });
  const complete = await service.enqueue(profile.slug, finish);
  assert.equal(complete.lastResult.state, 'saved');
  await service.enqueue(profile.slug, finish);
  const saved = await api.state(auth);
  assert.equal(saved.state.workouts.length, 1);
  assert.equal(saved.state.workouts[0].entries[0].sets[0].w, profile.slug === 'alpha' ? 12.5 : 5);
  assert.equal(saved.state.active, undefined); checks++;
  // Real stale-revision response, not a mock of the CAS implementation.
  assert.equal(await api.save(auth, saved.state, saved.rev - 1), false); checks++;
}
assert.equal((await api.request('/api/me', 'not-a-token')).status, 401); checks++;
console.log(JSON.stringify({ isolatedInstalledApi: true, checks, profiles: 2, savedOnceEach: true, productionTouched: false }));
