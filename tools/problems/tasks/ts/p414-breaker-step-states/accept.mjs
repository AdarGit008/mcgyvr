import assert from "node:assert/strict";
import { traceBreakerStates } from "./solution.ts";

const patient = { trip: 2, cool: 2, proof: 2 };

assert.deepEqual(
  traceBreakerStates(["fail", "fail", "pass", "fail", "pass", "pass"], patient),
  ["closed", "open", "open", "half", "half", "closed"],
  "the guard trips, waits out the countdown and earns its way back",
);
assert.deepEqual(
  traceBreakerStates(["fail", "fail", "pass", "pass", "fail"], patient),
  ["closed", "open", "open", "half", "open"],
  "one fail while half sends the guard back with a fresh countdown",
);
assert.deepEqual(
  traceBreakerStates(
    ["fail", "pass", "fail", "fail", "fail", "pass", "pass"],
    { trip: 3, cool: 1, proof: 1 },
  ),
  ["closed", "closed", "closed", "closed", "open", "half", "closed"],
  "a pass wipes the losing streak so three separated fails never trip",
);
assert.deepEqual(
  traceBreakerStates(["pass", "pass", "pass"], { trip: 1, cool: 1, proof: 1 }),
  ["closed", "closed", "closed"],
  "nothing but passes leaves the guard closed",
);
assert.deepEqual(
  traceBreakerStates(["fail"], { trip: 1, cool: 1, proof: 1 }),
  ["open"],
  "a trip of one opens on the first fail",
);
assert.deepEqual(
  traceBreakerStates(["fail", "pass", "pass"], { trip: 1, cool: 1, proof: 2 }),
  ["open", "half", "half"],
  "the outcome read while open is thrown away",
);
assert.deepEqual(
  traceBreakerStates(["fail", "fail", "fail", "fail"], { trip: 1, cool: 3, proof: 1 }),
  ["open", "open", "open", "half"],
  "a long countdown ignores every outcome it swallows",
);
assert.deepEqual(
  traceBreakerStates([], patient),
  [],
  "no steps give no postures",
);

assert.throws(
  () => traceBreakerStates("fail", patient),
  Error,
  "outcomes given as a string is rejected",
);
assert.throws(
  () => traceBreakerStates(["skip"], patient),
  Error,
  "an outcome outside the two words is rejected",
);
assert.throws(
  () => traceBreakerStates(["fail"], { trip: 2, cool: 2 }),
  Error,
  "settings without proof is rejected",
);
assert.throws(
  () => traceBreakerStates(["fail"], { trip: 0, cool: 2, proof: 2 }),
  Error,
  "a trip of zero is rejected",
);
assert.throws(
  () => traceBreakerStates(["fail"], { trip: 2, cool: -1, proof: 2 }),
  Error,
  "a negative cool is rejected",
);
assert.throws(
  () => traceBreakerStates(["fail"], { trip: 2, cool: 2, proof: 1.5 }),
  Error,
  "a fractional proof is rejected",
);
assert.throws(
  () => traceBreakerStates(["fail"], [2, 2, 2]),
  Error,
  "settings given as a list is rejected",
);
console.log("ok");
