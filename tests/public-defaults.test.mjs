import { test } from 'node:test';
import assert from 'node:assert/strict';
import { snapshot } from '../bridge/model.mjs';
import { CABLE_WEIGHTS_KG, validateCableWeights } from '../bridge/equipment.mjs';

test('generic install preserves native cable loads and does not inherit a machine calibration', () => {
  assert.deepEqual(CABLE_WEIGHTS_KG, []);
  const state = {
    unit: 'kg', week: { 0: 'r' }, dayPlan: {}, customEx: [], workouts: [], bodyweight: [],
    routines: [{ id: 'r', name: 'Synthetic', ex: [
      { id: '0861', weight: 17.25, sets: 2, reps: 10, prog: 'off' },
    ] }],
  };
  const before = structuredClone(state);
  const result = snapshot(state, 6, new Date('2026-11-01T12:00:00Z'), { enhanced: true });
  assert.equal(result.entries[0].sets.find(row => !row.warmup).weight, 17.25);
  assert.equal(result.entries[0].weightOptions, undefined);
  assert.deepEqual(state, before);
});

test('explicit cable calibration rejects malformed, duplicate or descending labels', () => {
  for (const value of [null, [], [0], [5, 10], [0, 5, 5], [0, 10, 5], [0, '5'], [0, Infinity]]) {
    assert.throws(() => validateCableWeights(value));
  }
  assert.deepEqual(validateCableWeights([0, 5, 10, 15]), [0, 5, 10, 15]);
});
