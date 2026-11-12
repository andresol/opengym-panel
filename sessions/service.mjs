import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { PanelError, beginSession, completedState, editRow, panelView, stateOf } from './model.mjs';
import { setsDoneActive } from '../vendor/opengym/frontend/src/lib/history.js';

const MAX_STATE = 8 * 1024 * 1024;
const clone = value => structuredClone(value);
const validSlug = value => typeof value === 'string' && /^[a-z][a-z0-9-]{0,30}$/.test(value);

function readJson(file, limit = MAX_STATE) {
  const fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
  try {
    const stat = fs.fstatSync(fd);
    if (!stat.isFile() || stat.size > limit) throw new Error('Invalid document');
    return JSON.parse(fs.readFileSync(fd, 'utf8'));
  } finally {
    fs.closeSync(fd);
  }
}

function atomicJson(file, value) {
  const directory = path.dirname(file);
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const temporary = path.join(directory, `.save-${crypto.randomUUID()}`);
  const fd = fs.openSync(temporary, 'wx', 0o600);
  try {
    fs.writeFileSync(fd, JSON.stringify(value));
    fs.fsyncSync(fd);
  } finally {
    fs.closeSync(fd);
  }
  try {
    fs.renameSync(temporary, file);
    const dir = fs.openSync(directory, 'r');
    try { fs.fsyncSync(dir); } finally { fs.closeSync(dir); }
  } catch (error) {
    try { fs.unlinkSync(temporary); } catch { /* No older record is removed. */ }
    throw error;
  }
}

export class OpenGymApi {
  constructor(base, fetcher = fetch) {
    const url = new URL(base);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('Invalid API origin');
    this.base = url.origin;
    this.fetcher = fetcher;
  }

  async request(route, token, method = 'GET', body = null) {
    const headers = { Accept: 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== null) headers['Content-Type'] = 'application/json';
    let response;
    try {
      response = await this.fetcher(this.base + route, {
        method, headers, body: body === null ? undefined : JSON.stringify(body),
        redirect: 'error', signal: AbortSignal.timeout(7000),
      });
    } catch {
      throw new PanelError('opengym_unavailable', 503);
    }
    const chunks = [];
    let bytes = 0;
    try {
      for await (const chunk of response.body) {
        bytes += chunk.length;
        if (bytes > MAX_STATE) throw new Error('Oversized response');
        chunks.push(chunk);
      }
      return { status: response.status, data: JSON.parse(Buffer.concat(chunks).toString('utf8')) };
    } catch {
      throw new PanelError('opengym_unavailable', 503);
    }
  }

  async identity(token) {
    const result = await this.request('/api/me', token);
    if (result.status === 401) throw new PanelError('pair_required', 401);
    if (result.status !== 200) throw new PanelError('opengym_unavailable', 503);
    const user = result.data.user || result.data;
    if (!user?.id) throw new PanelError('pair_required', 401);
    return { ...user, renewedToken: typeof result.data.token === 'string' ? result.data.token : null };
  }

  async redeem(code) {
    const result = await this.request('/api/pair/redeem', null, 'POST', { code });
    if (result.status !== 200 || typeof result.data.token !== 'string' || !result.data.user?.id) {
      throw new PanelError('invalid_pair_code');
    }
    return result.data;
  }

  async state(token) {
    const result = await this.request('/api/data', token);
    if (result.status === 401) throw new PanelError('pair_required', 401);
    if (result.status !== 200 || !Number.isInteger(result.data.rev)) throw new PanelError('opengym_unavailable', 503);
    return { state: stateOf(result.data.state), rev: result.data.rev };
  }

  async save(token, state, baseRev) {
    const result = await this.request('/api/data', token, 'PUT', { state, baseRev });
    if (result.status === 401) throw new PanelError('pair_required', 401);
    if (result.status === 409) return false;
    if (result.status !== 200 || result.data.ok !== true) throw new PanelError('save_unconfirmed', 503);
    return true;
  }
}

/** One serialized command stream per server-owned profile; no UID comes from a client. */
export class SessionService {
  constructor({ profiles, dataDir, storeDir, api, now = Date.now }) {
    this.bindings = new Map();
    for (const binding of profiles || []) {
      if (!validSlug(binding.slug) || !/^[A-Za-z0-9_-]{8,80}$/.test(binding.uid) ||
          !binding.name || this.bindings.has(binding.slug) || [...this.bindings.values()].some(existing => existing.uid === binding.uid)) throw new Error('Invalid profile binding');
      this.bindings.set(binding.slug, binding);
    }
    if (!this.bindings.size || this.bindings.size > 8) throw new Error('Missing profile bindings');
    this.dataDir = path.resolve(dataDir);
    this.storeDir = path.resolve(storeDir);
    fs.mkdirSync(this.storeDir, { recursive: true, mode: 0o700 });
    this.api = api;
    this.now = now;
    this.queues = new Map();
  }

  binding(slug) {
    const binding = this.bindings.get(slug);
    if (!binding) throw new PanelError('unknown_profile', 404);
    return binding;
  }

  file(slug) { this.binding(slug); return path.join(this.storeDir, `${slug}.json`); }

  record(slug) {
    try { return readJson(this.file(slug), 2 * 1024 * 1024); }
    catch (error) {
      if (error.code === 'ENOENT') return { seen: [] };
      throw new PanelError('draft_unavailable', 503);
    }
  }

  persist(slug, record) { atomicJson(this.file(slug), record); }

  source(slug) {
    const binding = this.binding(slug);
    try { return stateOf(readJson(path.join(this.dataDir, `state-${binding.uid}.json`))); }
    catch { throw new PanelError('source_unavailable', 503); }
  }

  view(slug, day = null, routine = null) {
    return panelView(this.source(slug), this.binding(slug), this.record(slug), day, this.now(), routine);
  }

  list() { return { profiles: [...this.bindings.values()].map(({ slug, name }) => ({ slug, name })) }; }

  enqueue(slug, command) {
    this.binding(slug);
    const previous = this.queues.get(slug) || Promise.resolve();
    const next = previous.catch(() => {}).then(() => this.apply(slug, command));
    const settled = next.catch(() => {});
    this.queues.set(slug, settled);
    return next.finally(() => { if (this.queues.get(slug) === settled) this.queues.delete(slug); });
  }

  checkpoint(record, command) {
    record.seen = [...(record.seen || []).slice(-127), command.requestId];
    return record;
  }

  assertSession(record, command) {
    if (!record.session || command.sessionId !== record.session.active.id || command.revision !== record.session.revision) {
      throw new PanelError('session_changed', 409);
    }
  }

  async assertIdentity(record, binding) {
    if (!record.token) throw new PanelError('pair_required', 401);
    const user = await this.api.identity(record.token);
    if (user.id !== binding.uid || user.admin === true) throw new PanelError('wrong_profile', 403);
    if (user.renewedToken) record.token = user.renewedToken;
  }

  backup(slug, state, rev) {
    const directory = path.join(this.storeDir, 'backups', slug);
    fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
    atomicJson(path.join(directory, `${String(this.now()).padStart(13, '0')}-${crypto.randomUUID()}.json`), { rev, state });
    // Bounded recovery copies belong only to this service; never touch OpenGym's backups.
    const owned = fs.readdirSync(directory).filter(name => /^\d{13}-[a-f0-9-]{36}\.json$/.test(name)).sort();
    let total = owned.reduce((bytes, name) => bytes + fs.lstatSync(path.join(directory, name)).size, 0);
    while (owned.length > 10 || (total > 32 * 1024 * 1024 && owned.length > 1)) {
      const file = path.join(directory, owned.shift());
      const stat = fs.lstatSync(file);
      if (!stat.isFile()) throw new PanelError('backup_unavailable', 503);
      total -= stat.size;
      fs.unlinkSync(file);
    }
  }

  async finish(slug, record) {
    const session = record.session;
    const binding = this.binding(slug);
    await this.assertIdentity(record, binding);
    for (let attempt = 0; attempt < 4; attempt++) {
      const fresh = await this.api.state(record.token);
      const result = completedState(fresh.state, session, this.now());
      if (result.empty) {
        record.lastResult = { state: 'closed', sessionId: session.active.id, finishedAt: this.now(), done: 0 };
        delete record.session;
        this.persist(slug, record);
        return;
      }
      if (!result.alreadySaved) {
        this.backup(slug, fresh.state, fresh.rev);
        if (!await this.api.save(record.token, result.state, fresh.rev)) continue;
      }
      // A timeout or lost response cannot turn a guess into "saved". Read back by stable id.
      const verified = await this.api.state(record.token);
      const saved = verified.state.workouts.find(workout => workout.id === session.active.id);
      if (!saved) throw new PanelError('save_unconfirmed', 503);
      record.lastResult = { state: 'saved', sessionId: session.active.id, finishedAt: this.now(),
        done: setsDoneActive(session.active) };
      delete record.session;
      this.persist(slug, record);
      return;
    }
    throw new PanelError('save_conflict', 409);
  }

  async retrySaving() {
    for (const slug of this.bindings.keys()) {
      const record = this.record(slug);
      if (record.token && record.session?.phase === 'saving' && !this.queues.has(slug)) {
        await this.enqueue(slug, { action: 'finish', requestId: crypto.randomUUID(),
          sessionId: record.session.active.id, revision: record.session.revision }).catch(() => {});
      }
    }
  }

  async apply(slug, command) {
    const binding = this.binding(slug);
    if (!command || typeof command.requestId !== 'string' || !/^[A-Za-z0-9_-]{16,64}$/.test(command.requestId) ||
        !['pair', 'start', 'set', 'finish', 'discard'].includes(command.action)) throw new PanelError('invalid_action');
    const allowed = new Set(['action', 'requestId', 'day', 'routine', 'code', 'sessionId', 'revision', 'exercise', 'row', 'side', 'done', 'weight', 'reps', 'seconds', 'minutes', 'speed']);
    if (Object.keys(command).some(key => !allowed.has(key))) throw new PanelError('invalid_action');
    const record = this.record(slug);
    const day = command.day ?? null;
    const routine = command.routine ?? null;
    if (routine !== null && (!['pair', 'start'].includes(command.action) || typeof routine !== 'string' || !/^[a-f0-9]{24}$/.test(routine))) throw new PanelError('invalid_routine');
    if (day !== null && (!Number.isInteger(day) || day < 0 || day > 6)) throw new PanelError('invalid_day');
    if ((record.seen || []).includes(command.requestId) ||
        (command.action === 'finish' && !record.session && record.lastResult?.sessionId === command.sessionId)) return this.view(slug, day, record.session ? null : routine);
    try {
      if (command.action === 'pair') {
        const code = typeof command.code === 'string' ? command.code.replace(/\s/g, '').toUpperCase() : '';
        if (!/^[A-HJ-NP-Z2-9]{8}$/.test(code)) throw new PanelError('invalid_pair_code');
        const paired = await this.api.redeem(code);
        if (paired.user.id !== binding.uid || paired.user.admin === true) throw new PanelError('wrong_profile', 403);
        record.token = paired.token;
        this.checkpoint(record, command);
        this.persist(slug, record);
      } else if (command.action === 'start') {
        if (!record.session) {
          await this.assertIdentity(record, binding);
          const fresh = await this.api.state(record.token);
          record.session = beginSession(fresh.state, day, this.now(), { binding, routine });
          delete record.lastResult;
        }
        this.checkpoint(record, command);
        this.persist(slug, record);
      } else {
        this.assertSession(record, command);
        if (command.action === 'set') {
          record.session = editRow(record.session, command, this.now());
          this.checkpoint(record, command);
          this.persist(slug, record);
        } else if (command.action === 'discard') {
          if (record.session.phase !== 'active') throw new PanelError('save_in_progress', 409);
          delete record.session;
          record.lastResult = { state: 'discarded', finishedAt: this.now() };
          this.checkpoint(record, command);
          this.persist(slug, record);
        } else {
          if (record.session.phase === 'active') {
            record.session.phase = 'saving';
            record.session.end = this.now();
            this.persist(slug, record);
          }
          await this.finish(slug, record);
          this.checkpoint(record, command);
          this.persist(slug, record);
        }
      }
    } catch (error) {
      if (error instanceof PanelError && error.code === 'pair_required') {
        delete record.token;
        this.persist(slug, record);
      }
      throw error;
    }
    return this.view(slug, day, record.session ? null : routine);
  }
}
