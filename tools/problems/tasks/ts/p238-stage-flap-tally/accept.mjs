import assert from "node:assert/strict";
import { tallyStageRetries } from "./solution.ts";

const stage = (name, outcomes) => ({ name, outcomes });

assert.deepEqual(
  tallyStageRetries([], 3),
  ["* 0 0 0 0 0"],
  "an empty pipeline still reports its rollup",
);
assert.deepEqual(
  tallyStageRetries([stage("a", ["pass"])], 3),
  ["a 1 0 0 0 green", "* 1 0 0 0 1"],
  "one clean attempt costs no retry",
);
assert.deepEqual(
  tallyStageRetries([stage("a", ["flap", "pass"])], 3),
  ["a 2 1 1 0 green", "* 2 1 1 0 1"],
  "a wobble that came good is still green",
);
assert.deepEqual(
  tallyStageRetries([stage("a", ["flap", "halt"])], 3),
  ["a 2 1 1 1 dead", "* 2 1 1 1 0"],
  "a halt after a flap counts on both columns",
);
assert.deepEqual(
  tallyStageRetries([stage("a", ["flap", "flap", "flap"])], 3),
  ["a 3 2 3 0 spent", "* 3 2 3 0 0"],
  "flapping to the last allowed attempt is spent",
);
assert.deepEqual(
  tallyStageRetries([stage("a", ["flap"])], 3),
  ["a 1 0 1 0 open", "* 1 0 1 0 0"],
  "flapping with budget to spare is open",
);
assert.deepEqual(
  tallyStageRetries([stage("a", ["flap"])], 1),
  ["a 1 0 1 0 spent", "* 1 0 1 0 0"],
  "a budget of one makes the first flap the last",
);
assert.deepEqual(
  tallyStageRetries(
    [
      stage("build", ["flap", "pass"]),
      stage("test", ["halt"]),
      stage("ship", ["flap"]),
    ],
    2,
  ),
  [
    "build 2 1 1 0 green",
    "test 1 0 0 1 dead",
    "ship 1 0 1 0 open",
    "* 4 1 2 1 1",
  ],
  "stages keep their order and the rollup sums every column",
);
assert.throws(
  () => tallyStageRetries([stage("a", ["pass", "flap"])], 3),
  Error,
  "nothing may follow a pass",
);
assert.throws(
  () => tallyStageRetries([stage("a", ["halt", "flap"])], 3),
  Error,
  "nothing may follow a halt",
);
assert.throws(
  () => tallyStageRetries([stage("a", ["flap", "flap", "flap", "flap"])], 3),
  Error,
  "a stage over budget could never have happened",
);
assert.throws(
  () => tallyStageRetries([stage("a", [])], 3),
  Error,
  "a stage with no outcomes is rejected",
);
assert.throws(
  () => tallyStageRetries([stage("a", ["boom"])], 3),
  Error,
  "a word outside the three is rejected",
);
assert.throws(
  () => tallyStageRetries([stage("a", ["pass"]), stage("a", ["pass"])], 3),
  Error,
  "a repeated stage name is rejected",
);
assert.throws(
  () => tallyStageRetries([stage("two words", ["pass"])], 3),
  Error,
  "a name holding a space is rejected",
);
assert.throws(
  () => tallyStageRetries([stage("a", ["pass"])], 0),
  Error,
  "a budget below one is rejected",
);
console.log("ok");
