import assert from "node:assert/strict";
import { chargeStages } from "./solution.ts";

const stage = (name, ...tries) => ({
  name,
  tries: tries.map(([secs, code]) => ({ secs, code })),
});

assert.deepEqual(chargeStages([], 1), [], "an empty pipeline bills nothing");
assert.deepEqual(
  chargeStages([stage("a", [5, "done"])], 1),
  [{ name: "a", wall: 5, billed: 5, free: 0 }],
  "a clean run is billed in full",
);
assert.deepEqual(
  chargeStages([stage("a", [6, "hard"])], 1),
  [{ name: "a", wall: 6, billed: 6, free: 0 }],
  "a terminal failure is billed, never forgiven",
);
assert.deepEqual(
  chargeStages([stage("a", [3, "soft"], [7, "done"])], 1),
  [{ name: "a", wall: 10, billed: 7, free: 3 }],
  "the first wobble is on the house",
);
assert.deepEqual(
  chargeStages([stage("a", [3, "soft"], [4, "soft"], [7, "done"])], 1),
  [{ name: "a", wall: 14, billed: 11, free: 3 }],
  "the second wobble is past the allowance and is billed",
);
assert.deepEqual(
  chargeStages([stage("a", [3, "soft"], [7, "done"])], 0),
  [{ name: "a", wall: 10, billed: 10, free: 0 }],
  "forgiving nothing bills every second",
);
assert.deepEqual(
  chargeStages([stage("a", [3, "soft"], [4, "soft"], [7, "done"])], 5),
  [{ name: "a", wall: 14, billed: 7, free: 7 }],
  "an allowance larger than the wobbles leaves no soft second billed",
);
assert.deepEqual(
  chargeStages(
    [stage("a", [2, "soft"], [2, "done"]), stage("b", [5, "soft"], [5, "hard"])],
    1,
  ),
  [
    { name: "a", wall: 4, billed: 2, free: 2 },
    { name: "b", wall: 10, billed: 5, free: 5 },
  ],
  "each stage draws on its own allowance",
);
assert.deepEqual(
  chargeStages([stage("a", [0, "soft"], [0, "done"])], 0),
  [{ name: "a", wall: 0, billed: 0, free: 0 }],
  "attempts of no length bill nothing",
);
assert.throws(
  () => chargeStages([stage("a", [1, "done"], [1, "soft"])], 1),
  Error,
  "nothing may run after a done",
);
assert.throws(
  () => chargeStages([stage("a", [1, "hard"], [1, "soft"])], 1),
  Error,
  "nothing may run after a hard",
);
assert.throws(
  () => chargeStages([stage("a", [1, "wobbly"])], 1),
  Error,
  "an unknown code is rejected",
);
assert.throws(
  () => chargeStages([stage("a", [-1, "done"])], 1),
  Error,
  "a negative duration is rejected",
);
assert.throws(
  () => chargeStages([{ name: "a", tries: [] }], 1),
  Error,
  "a stage that ran nothing is rejected",
);
assert.throws(
  () => chargeStages([stage("a", [1, "done"]), stage("a", [1, "done"])], 1),
  Error,
  "a repeated stage name is rejected",
);
assert.throws(
  () => chargeStages([stage("a", [1, "done"])], -1),
  Error,
  "a negative allowance is rejected",
);
console.log("ok");
