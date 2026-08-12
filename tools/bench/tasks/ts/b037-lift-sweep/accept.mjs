import assert from "node:assert/strict";
import { liftDistance, runLift, splitCalls, sweepReport } from "./solution.ts";

assert.deepEqual(runLift(5, []), [], "no calls yields no stops");
assert.deepEqual(
  runLift(4, [[4, "up"], [6, "up"]]),
  [4, 6],
  "an up call at the boarding floor is served first",
);
assert.deepEqual(
  runLift(5, [[2, "up"], [8, "up"], [6, "down"], [1, "down"], [5, "up"]]),
  [5, 8, 6, 1, 2],
  "up sweep, then down sweep, then the up calls left behind",
);
assert.deepEqual(
  runLift(0, [[3, "down"], [9, "down"], [6, "down"]]),
  [9, 6, 3],
  "the down sweep runs highest floor first",
);
assert.deepEqual(
  runLift(10, [[2, "up"], [7, "down"]]),
  [7, 2],
  "a behind up call waits until the down sweep is done",
);
assert.deepEqual(runLift(1, [[4, "up"], [4, "up"]]), [4], "repeated calls collapse");
assert.deepEqual(
  runLift(1, [[4, "up"], [4, "down"]]),
  [4, 4],
  "both directions at one floor are two stops",
);
assert.deepEqual(
  runLift(4, [[4, "down"]]),
  [4],
  "a down call at the boarding floor is served on the down sweep",
);
assert.deepEqual(
  runLift(9, [[3, "up"], [5, "up"]]),
  [3, 5],
  "behind up calls run ascending",
);
assert.deepEqual(
  runLift(6, [
    [6, "up"],
    [11, "up"],
    [2, "up"],
    [9, "down"],
    [4, "down"],
    [10, "up"],
    [4, "down"],
  ]),
  [6, 10, 11, 9, 4, 2],
  "a full mixed sweep over all three phases",
);
assert.deepEqual(
  splitCalls(5, [[7, "up"], [2, "up"], [5, "up"], [8, "down"], [3, "down"]]),
  { upAhead: [5, 7], upBehind: [2], down: [3, 8] },
  "splitCalls sorts each part ascending",
);
assert.deepEqual(
  splitCalls(4, []),
  { upAhead: [], upBehind: [], down: [] },
  "splitCalls of no calls is three empty parts",
);
assert.equal(liftDistance(5, []), 0, "no stops means no travel");
assert.equal(liftDistance(5, [8, 3, 6]), 11, "travel sums each leg");
assert.deepEqual(
  sweepReport(3, []),
  { stops: [], travelled: 0, reversals: 0 },
  "an idle sweep reports zeros",
);
assert.deepEqual(
  sweepReport(5, [[8, "up"], [2, "down"]]),
  { stops: [8, 2], travelled: 9, reversals: 1 },
  "one reversal turning from up to down",
);
assert.deepEqual(
  sweepReport(4, [[4, "up"], [6, "up"], [1, "down"]]),
  { stops: [4, 6, 1], travelled: 7, reversals: 1 },
  "a zero-length move counts no reversal",
);
assert.throws(() => runLift("x", []), Error, "non-integer boarding floor");
assert.throws(() => runLift(1, "x"), Error, "non-list calls");
assert.throws(() => runLift(1, [[2]]), Error, "a one-item call");
assert.throws(() => runLift(1, [[2.5, "up"]]), Error, "a fractional floor");
assert.throws(() => runLift(1, [[2, "sideways"]]), Error, "a bad direction");
assert.throws(() => liftDistance(1, [2.5]), Error, "a fractional stop");
assert.throws(() => liftDistance(1, "x"), Error, "non-list stops");
console.log("ok");
