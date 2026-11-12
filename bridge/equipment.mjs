/** Physical stack, not handle resistance: no unverified pulley conversion. */
import { CATALOGUE } from '../vendor/opengym/frontend/src/lib/exercises.js';
import { modeOf } from '../vendor/opengym/frontend/src/lib/history.js';
import { syncGymInventory } from '../vendor/opengym/frontend/src/lib/gym-inventory.js';

// No machine-specific snapping unless the installer explicitly supplies a table.
// The settings are process-local and never written into an OpenGym profile.
export function validateCableWeights(value) {
  if (!Array.isArray(value) || value.length < 2 || value.length > 24 || value[0] !== 0 ||
      value.some((w, i) => typeof w !== 'number' || !Number.isFinite(w) || w < 0 ||
        w > 2000 || (i > 0 && w <= value[i - 1]))) {
    throw new Error('PANEL_CABLE_WEIGHTS_KG must be ascending numeric labels starting with zero');
  }
  return Object.freeze([...value]);
}
export let CABLE_WEIGHTS_KG = Object.freeze([]);
export let CABLE_STEP_KG = 0;
export let CABLE_MAX_KG = 0;
export let CABLE_PLATES = 0;
export function configureCableWeights(weights) {
  CABLE_WEIGHTS_KG = validateCableWeights(weights);
  CABLE_STEP_KG = (CABLE_WEIGHTS_KG.at(-1) - CABLE_WEIGHTS_KG[1]) / (CABLE_WEIGHTS_KG.length - 2 || 1);
  if (CABLE_WEIGHTS_KG.length === 2) CABLE_STEP_KG = CABLE_WEIGHTS_KG[1];
  CABLE_MAX_KG = CABLE_WEIGHTS_KG.at(-1);
  CABLE_PLATES = CABLE_WEIGHTS_KG.length - 1;
}
if (process.env.PANEL_CABLE_WEIGHTS_KG) {
  configureCableWeights(JSON.parse(process.env.PANEL_CABLE_WEIGHTS_KG));
}
export const isCable = (state, id) => CABLE_WEIGHTS_KG.length > 1 && state.unit !== 'lb' &&
  (state.customEx?.find(ex => ex.id === id) || CATALOGUE.find(ex => ex.id === id))?.eq === 'cable';
export function cableWeight(value) {
  if (!CABLE_WEIGHTS_KG.length) return value;
  if (!(value > 0)) return 0;
  return CABLE_WEIGHTS_KG.slice(1).reduce((nearest, weight) =>
    Math.abs(weight - value) < Math.abs(nearest - value) ? weight : nearest);
}
/** Prospective panel prescriptions only; source routines/history remain untouched. */
export function equipmentState(state) {
  // Reconcile the selected gym only in this projection, never in authoritative data.
  const projected = structuredClone(state);
  syncGymInventory(projected);
  return { ...projected, routines: projected.routines.map(routine => ({ ...routine,
    ex: routine.ex.map(cfg => isCable(state, cfg.id) && modeOf(cfg) === 'reps'
      ? { ...cfg, inc: CABLE_STEP_KG } : cfg),
  })) };
}
export function equipmentEntries(state, entries) {
  for (const entry of entries) {
    if (!isCable(state, entry.id) || modeOf(entry.target) === 'cardio') continue;
    for (const row of entry.sets) {
      row.w = cableWeight(row.w);
      if (row.sides) {
        row.sides.L.w = cableWeight(row.sides.L.w);
        row.sides.R.w = cableWeight(row.sides.R.w);
      }
    }
    entry.target.weight = cableWeight(entry.target.weight);
  }
  return entries;
}
export const cableControls = (state, id) => isCable(state, id)
  ? { weightStep: CABLE_STEP_KG, weightMax: CABLE_MAX_KG, weightOptions: [...CABLE_WEIGHTS_KG] } : {};
