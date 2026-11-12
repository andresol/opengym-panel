/** OpenGym-native workout semantics, with a small panel-only public projection. */
import crypto from 'node:crypto';
import { buildCombinedEntries, deriveSessionName } from '../vendor/opengym/frontend/src/lib/session-merge.js';
import { buildCompletedWorkout } from '../vendor/opengym/frontend/src/lib/finish-workout.js';
import {
  bestWeightFor, bestWeightForEntry, effectiveRoutines, isBw, modeOf,
  setsDoneActive, setUnitsTotal, workoutVolume,
} from '../vendor/opengym/frontend/src/lib/history.js';
import { CATALOGUE, EXIDX, beatsWeight, betterWeight, canonicalExId, exOr, registerCustom } from '../vendor/opengym/frontend/src/lib/exercises.js';
import { hasCompletedWork, isSideSet, isWarmupRow, syncSideAggregate } from '../vendor/opengym/frontend/src/lib/workout-model.js';
import { inUnitOf } from '../vendor/opengym/frontend/src/lib/sync-merge.js';
import { exerciseMuscleSnapshot } from '../vendor/opengym/frontend/src/lib/muscles.js';
import { clean, localDate, num, selectedDate, snapshot } from '../bridge/model.mjs';
import { equipmentState, equipmentEntries, cableControls } from '../bridge/equipment.mjs';
import { musclesOf, MUSCLES } from '../vendor/opengym/frontend/src/lib/muscles.js';
import { mediaAsset } from '../bridge/catalogue-media.mjs';
import { activeGym } from '../vendor/opengym/frontend/src/lib/gym-inventory.js';
import { names } from '../preview/names.mjs';

export const VERSION = '1.2.0';
export const OPENGYM_VERSION = '1.4.4';
const clone = value => structuredClone(value);

export class PanelError extends Error {
  constructor(code, status = 400) {
    super(code);
    this.code = code;
    this.status = status;
  }
}

export function stateOf(raw) {
  if (!raw || !Array.isArray(raw.routines) || !Array.isArray(raw.workouts)) {
    throw new PanelError('source_unavailable', 503);
  }
  return { ...raw, week: raw.week || {}, dayPlan: raw.dayPlan || {}, customEx: raw.customEx || [],
    exWeights: raw.exWeights || {}, bodyweight: raw.bodyweight || [], unit: raw.unit === 'lb' ? 'lb' : 'kg' };
}

const routineKey = (binding, routine) => crypto.createHash('sha256')
  .update(JSON.stringify(['panel-routine-v1', binding.uid, routine.id])).digest('hex').slice(0, 24);

function choicesFor(state, binding) {
  return state.routines.filter(r => typeof r.id === 'string' && Array.isArray(r.ex) && r.ex.length > 0 && r.ex.length <= 40)
    .slice(0, 32).map(r => ({ key: routineKey(binding, r), name: clean(r.name || r.n || 'Treningsøkt', 160) }));
}

/** Preview an existing own routine without writing week/dayPlan or a workout. */
function selectedPlan(state, binding, day, now, routine) {
  if (routine == null) return state;
  if (typeof routine !== 'string' || !/^[a-f0-9]{24}$/.test(routine) || !binding?.uid) throw new PanelError('invalid_routine');
  const { date } = selectedDate(day, new Date(now));
  if (effectiveRoutines(state, date).some(r => r.ex?.length)) throw new PanelError('not_rest_day');
  const allowed = choicesFor(state, binding).some(choice => choice.key === routine);
  const chosen = allowed && state.routines.find(r => routineKey(binding, r) === routine);
  if (!chosen) throw new PanelError('routine_unavailable', 409);
  return { ...state, dayPlan: { ...state.dayPlan, [date]: chosen.id } };
}

export function beginSession(raw, day, now = Date.now(), selection = {}) {
  const state = equipmentState(selectedPlan(stateOf(raw), selection.binding, day, now, selection.routine));
  registerCustom(state.customEx);
  const selected = selectedDate(day, new Date(now));
  state.active = { d: selected.date };
  const planned = effectiveRoutines(state, selected.date);
  if (!planned.length) throw new PanelError('no_planned_workout');
  const built = buildCombinedEntries(state, planned.map(routine => routine.id));
  equipmentEntries(state, built.entries);
  if (!built.entries.length || built.entries.length > 40 || built.entries.some(e => e.sets.length > 24 || e.sets.some(row => row.type === 'dropset' || row.type === 'restpause' || [row.sides?.L, row.sides?.R].some(side => side?.type === 'dropset' || side?.type === 'restpause')))) {
    throw new PanelError('unsupported_workout');
  }
  // Starting never marks a prescribed row as performed.
  for (const entry of built.entries) for (const row of entry.sets) {
    row.done = false;
    if (isSideSet(row)) {
      row.sides.L.done = false;
      row.sides.R.done = false;
    }
  }
  return {
    phase: 'active', revision: 1, unit: state.unit, planDay: selected.day,
    customEx: clone(state.customEx), planNotes: clone(state.exNotes || {}),
    active: {
      id: crypto.randomUUID(), d: localDate(new Date(now)), start: now,
      routineIds: built.routineIds,
      name: deriveSessionName(built.routines.map(routine => routine.name)) || 'Treningsøkt',
      bw: null, cur: 0, entries: clone(built.entries),
      ...(activeGym(state) ? { gym: { id: activeGym(state).id, name: activeGym(state).name } } : {}),
    },
  };
}

/** Carry changed values, never completion, to later pending work in this entry. */
function forwardRegisteredValues(entry, from, side, before, registered) {
  const fields = ['w', 'r', 'sec', 'min', 'speed']
    .filter(field => registered[field] !== before[field]);
  if (!fields.length || isWarmupRow(entry.sets[from])) return;

  for (let index = from + 1; index < entry.sets.length; index++) {
    const row = entry.sets[index];
    if (isWarmupRow(row) || isSideSet(row) !== (side !== null)) continue;
    const pending = side === null ? row : row.sides[side];
    if (pending.done === true) continue;

    for (const field of fields) pending[field] = registered[field];
    if (fields.includes('w')) pending.weightOrigin = 'manual';
    if (side !== null) entry.sets[index] = syncSideAggregate(row);
  }
}

/** Register one row/side and reuse its explicit changes for later pending work. */
export function editRow(session, { exercise, row, side = null, done, weight, reps, seconds, minutes, speed }, now = Date.now()) {
  if (!session || session.phase !== 'active') throw new PanelError('no_active_workout', 409);
  if (!Number.isInteger(exercise) || !Number.isInteger(row)) throw new PanelError('invalid_set');
  const entry = session.active.entries[exercise];
  const previous = entry?.sets?.[row];
  if (!previous) throw new PanelError('invalid_set');
  const perSide = isSideSet(previous);
  if (perSide ? !['L', 'R'].includes(side) : side !== null) throw new PanelError('invalid_side');
  const mode = modeOf(entry.target || {});
  const target = clone(perSide ? previous.sides[side] : previous);
  const numeric = (value, max, integer = false) => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > max ||
        (integer && !Number.isInteger(value))) throw new PanelError('invalid_value');
    return value;
  };
  if (weight !== undefined) {
    target.w = numeric(weight, 10000);
    target.weightOrigin = 'manual';
  }
  if (reps !== undefined) {
    if (mode !== 'reps') throw new PanelError('invalid_value');
    target.r = numeric(reps, 1000, true);
  }
  if (seconds !== undefined) {
    if (mode !== 'time') throw new PanelError('invalid_value');
    target.sec = numeric(seconds, 7200, true);
  }
  if (minutes !== undefined || speed !== undefined) {
    if (mode !== 'cardio') throw new PanelError('invalid_value');
    if (minutes !== undefined) target.min = numeric(minutes, 1440);
    if (speed !== undefined) target.speed = numeric(speed, 100);
  }
  if (done !== undefined) {
    if (typeof done !== 'boolean') throw new PanelError('invalid_value');
    if (done && target.done !== true) target.at = now;
    if (!done) delete target.at;
    target.done = done;
  }
  if (target.done && (mode === 'reps' ? !(target.r > 0) : mode === 'time' ? !(target.sec > 0) : !(target.min > 0))) {
    throw new PanelError('enter_result');
  }
  const next = clone(session);
  next.active.entries[exercise].sets[row] = perSide
    ? syncSideAggregate({ ...previous, sides: { ...previous.sides, [side]: target } })
    : target;
  if (perSide && done !== undefined) {
    const combined = next.active.entries[exercise].sets[row];
    const times = [combined.sides.L, combined.sides.R]
      .filter(result => result.done && Number.isFinite(result.at)).map(result => result.at);
    if (times.length) combined.at = Math.max(...times);
    else delete combined.at;
  }
  if (done === true) {
    forwardRegisteredValues(next.active.entries[exercise], row, side,
      perSide ? previous.sides[side] : previous, target);
  }
  next.revision++;
  return next;
}

/** Append to a fresh authoritative document; never replace history or routines. */
export function completedState(raw, session, now = Date.now()) {
  const state = stateOf(raw);
  const already = state.workouts.find(workout => workout.id === session.active.id);
  if (already) return { state: null, workout: already, alreadySaved: true };
  registerCustom(state.customEx);
  if (!session.active.entries.some(entry => entry.sets.some(hasCompletedWork))) {
    return { state: null, workout: null, empty: true };
  }
  const active = inUnitOf({ unit: session.unit, active: session.active }, state).active;
  // Match the app's finish path: a PR requires a completed, non-warm-up row.
  const prs = active.entries.filter(entry => {
    const loads = entry.sets.filter(row => row.done && !isWarmupRow(row)).map(row => row.w).filter(weight => weight > 0);
    const best = loads.length ? loads.reduce((a, b) => betterWeight(entry.id, a, b)) : 0;
    return beatsWeight(entry.id, best, bestWeightFor(state, entry.id));
  }).map(entry => entry.id);
  const workout = buildCompletedWorkout(active, {
    end: session.end || now, prs,
    snapshotFor: entry => EXIDX[entry.id]?.custom ? exerciseMuscleSnapshot(EXIDX[entry.id]) : null,
  });
  workout.vol = workoutVolume(workout);
  const next = clone(state);
  for (const entry of workout.entries) {
    const top = bestWeightForEntry(entry);
    if (top > 0 && beatsWeight(entry.id, top, next.exWeights[entry.id]?.w || 0)) {
      next.exWeights[entry.id] = { w: top, d: workout.d };
    }
  }
  next.workouts.push(workout);
  next._ts = now;
  delete next.active;
  return { state: next, workout, alreadySaved: false };
}

function publicRow(row, openWeight) {
  const result = {
    warmup: isWarmupRow(row), done: row.done === true,
    weight: openWeight && !row.weightOrigin && !row.done ? null : num(row.w),
    reps: num(row.r), seconds: num(row.sec), minutes: num(row.min), speed: num(row.speed),
  };
  if (isSideSet(row)) {
    result.sides = Object.fromEntries(['L', 'R'].map(side => [side, publicRow(row.sides[side], openWeight)]));
  }
  return result;
}

function projectActive(session, binding) {
  registerCustom(session.customEx || []);
  return session.active.entries.map(entry => {
    const cfg = entry.target || {};
    const custom = (session.customEx || []).find(exercise => exercise.id === entry.id);
    const known = custom || exOr(entry.id);
    const mode = modeOf(cfg), bodyweight = isBw(cfg);
    const work = entry.sets.filter(row => !isWarmupRow(row));
    const first = work[0] || {};
    const openWeight = !bodyweight && num(first.w) === 0 && num(cfg.weight) === 0;
    const weight = num(first.w);
    const source = CATALOGUE.find(exercise => exercise.id === canonicalExId(binding.mediaAliases?.[entry.id] || (!custom ? entry.id : null)));
    const restSeconds = cfg.restSec == null ? 90 : num(cfg.restSec, 3600);
    const warmups = entry.sets.filter(isWarmupRow).length;
    const detail = [mode === 'reps' && first.sides ? `V ${num(first.sides.L.r)} · H ${num(first.sides.R.r)} reps` : mode === 'reps' && cfg.side ? `${num(first.r) / 2} per side · ${num(first.r)} totalt` : null,
      warmups ? `${warmups} oppvarmingssett` : null, `Pause ${restSeconds} sek`].filter(Boolean).join(' · ');
    return {
      name: clean(!custom && names[entry.id] ? names[entry.id] : known.n || known.name, 480),
      target: mode === 'time' ? `${work.length} × ${num(first.sec)} sek`
        : mode === 'cardio' ? `${num(first.min)} min` : `${work.length} × ${num(first.r)}`,
      load: openWeight ? 'Valgfri vekt' : weight > 0 ? `${weight} ${session.unit}` : bodyweight ? 'Kroppsvekt' : 'Uten ekstra vekt',
      detail, restSeconds, note: clean(entry.note || cfg.note || session.planNotes?.[entry.id], 1000),
      mode, unit: session.unit, bodyweight, perSide: !!cfg.side,
      ...cableControls(session, entry.id), muscles: MUSCLES.map(m => Math.min(1, musclesOf(known)[m] || 0)),
      image: mediaAsset('img', source), animation: mediaAsset('gif', source),
      sets: entry.sets.map(row => publicRow(row, openWeight)),
    };
  });
}

export function panelView(raw, binding, record, day, now = Date.now(), routine = null) {
  const state = stateOf(raw);
  const session = record?.session || null;
  const options = {
    profile: binding.name, enhanced: true, mediaAliases: binding.mediaAliases, names,
  };
  let data = snapshot(state, session ? session.planDay : day, new Date(now), options);
  const resting = data.state === 'rest';
  if (!session && routine != null) {
    const preview = snapshot(selectedPlan(state, binding, day, now, routine), day, new Date(now), options);
    // A one-off choice must not make the saved weekly schedule look changed.
    data = { ...preview, week: data.week };
  }
  data.routineChoices = !session && resting ? choicesFor(state, binding) : [];
  data.routineSelection = !session ? routine : null;
  data.version = VERSION;
  data.opengymVersion = OPENGYM_VERSION;
  data.profileSlug = binding.slug;
  data.paired = !!record?.token;
  data.serverNow = now;
  data.session = session ? {
    id: session.active.id, revision: session.revision, phase: session.phase,
    startedAt: session.active.start,
    done: setsDoneActive(session.active), total: setUnitsTotal(session.active.entries),
    volume: Math.round(workoutVolume(session.active) * 100) / 100, unit: session.unit,
  } : null;
  data.lastResult = record?.lastResult || null;
  if (session) {
    data.date = session.active.d;
    data.title = clean(session.active.name, 640);
    data.state = 'active';
    data.entries = projectActive(session, binding);
  }
  // Exclude polling time from the semantic revision, not session edits or pairing state.
  const { fetchedAt, serverNow, revision, ...semantic } = data;
  data.revision = crypto.createHash('sha256').update(JSON.stringify(semantic)).digest('hex').slice(0, 16);
  return data;
}
