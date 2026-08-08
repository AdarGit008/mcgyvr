import assert from "node:assert/strict";
import { flagProbeReadings } from "./solution.ts";

const band = { low: 0, high: 100, jump: 10, stuck: 3 };

assert.deepEqual(
  flagProbeReadings([50, 55, 90, 90, 90, 90, 120, 95, 95], band),
  [[], [], ["jump"], [], ["stuck"], ["stuck"], ["range"], [], []],
  "a mixed line flags the jump, the long run, and the out-of-band value",
);
assert.deepEqual(
  flagProbeReadings([7], { low: 0, high: 10, jump: 1, stuck: 2 }),
  [[]],
  "a single plausible reading is unremarkable",
);
assert.deepEqual(
  flagProbeReadings([7], { low: 8, high: 10, jump: 1, stuck: 2 }),
  [["range"]],
  "a single reading beneath low is out of band",
);
assert.deepEqual(
  flagProbeReadings([200, 200, 200], { low: 0, high: 100, jump: 5, stuck: 2 }),
  [["range"], ["range", "stuck"], ["range", "stuck"]],
  "range and stuck may land on the same reading, in that order",
);
assert.deepEqual(
  flagProbeReadings([0, 40, 40], { low: 0, high: 100, jump: 10, stuck: 2 }),
  [[], ["jump"], ["stuck"]],
  "a repeated jumped-to value stops jumping and starts sticking",
);
assert.deepEqual(
  flagProbeReadings([5, 5, 6], { low: 0, high: 10, jump: 0, stuck: 5 }),
  [[], [], ["jump"]],
  "a jump of zero makes any change a jump",
);
assert.deepEqual(
  flagProbeReadings([-5, -20, -21], { low: -20, high: 20, jump: 100, stuck: 9 }),
  [[], [], ["range"]],
  "readings may be negative and low may be negative",
);
assert.deepEqual(
  flagProbeReadings([10, 300, 12], { low: 0, high: 100, jump: 5, stuck: 4 }),
  [[], ["range"], []],
  "the out-of-band reading is skipped when the next reading looks back",
);
assert.deepEqual(
  flagProbeReadings([10, 300, 40], { low: 0, high: 100, jump: 5, stuck: 4 }),
  [[], ["range"], ["jump"]],
  "the comparison still reaches back past the out-of-band reading",
);
assert.deepEqual(
  flagProbeReadings([4, 4, 4, 4, 9, 9, 4], { low: 0, high: 20, jump: 9, stuck: 3 }),
  [[], [], ["stuck"], ["stuck"], [], [], []],
  "a changed value opens a run of length one",
);
assert.deepEqual(
  flagProbeReadings([300, 300], { low: 0, high: 100, jump: 5, stuck: 3 }),
  [["range"], ["range"]],
  "an out-of-band run shorter than stuck carries range alone",
);

assert.throws(() => flagProbeReadings([], band), Error, "an empty list is rejected");
assert.throws(() => flagProbeReadings("50", band), Error, "a non-list is rejected");
assert.throws(
  () => flagProbeReadings([1, 2.5], band),
  Error,
  "a fractional reading is rejected",
);
assert.throws(() => flagProbeReadings([1], null), Error, "a null mapping is rejected");
assert.throws(() => flagProbeReadings([1], [0, 100, 10, 3]), Error, "a list of rules is rejected");
assert.throws(
  () => flagProbeReadings([1], { low: 0, high: 100, jump: 10 }),
  Error,
  "a missing stuck is rejected",
);
assert.throws(
  () => flagProbeReadings([1], { low: 100, high: 0, jump: 10, stuck: 3 }),
  Error,
  "low above high is rejected",
);
assert.throws(
  () => flagProbeReadings([1], { low: 0, high: 100, jump: -1, stuck: 3 }),
  Error,
  "a negative jump is rejected",
);
assert.throws(
  () => flagProbeReadings([1], { low: 0, high: 100, jump: 10, stuck: 1 }),
  Error,
  "a stuck of one is rejected",
);
console.log("ok");
