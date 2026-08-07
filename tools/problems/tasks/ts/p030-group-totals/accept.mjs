import assert from "node:assert/strict";
import { groupTotals } from "./solution.ts";

assert.deepEqual(
  groupTotals([{ g: "a", n: 1 }, { g: "a", n: 2 }, { g: "b", n: 5 }], "g", "n"),
  [["b", 5], ["a", 3]],
  "amounts accumulate and totals sort descending",
);
assert.deepEqual(
  groupTotals(
    [{ g: "beta", n: 4 }, { g: "alpha", n: 4 }, { g: "gamma", n: 4 }],
    "g",
    "n",
  ),
  [["alpha", 4], ["beta", 4], ["gamma", 4]],
  "equal totals fall back to label order",
);
assert.deepEqual(
  groupTotals(
    [{ g: "x", n: 1 }, { g: "y", n: 9 }, { g: "x", n: 3 }, { g: "z", n: 2 }],
    "g",
    "n",
  ),
  [["y", 9], ["x", 4], ["z", 2]],
  "three labels ranked by summed total",
);
assert.deepEqual(
  groupTotals([{ g: "a", n: 5 }, { g: "a", n: -2 }], "g", "n"),
  [["a", 3]],
  "negative amounts subtract",
);
assert.deepEqual(
  groupTotals([{ team: "red", pts: 2 }, { team: "red", pts: 2 }], "team", "pts"),
  [["red", 4]],
  "property names come from the arguments",
);
assert.deepEqual(groupTotals([], "g", "n"), [], "no rows, no totals");
assert.throws(() => groupTotals([{ g: "a" }], "g", "n"), Error, "missing amount rejected");
assert.throws(() => groupTotals([{ n: 1 }], "g", "n"), Error, "missing label rejected");
assert.throws(() => groupTotals([{ g: 7, n: 1 }], "g", "n"), Error, "non-string label rejected");
assert.throws(() => groupTotals([{ g: "a", n: 1.5 }], "g", "n"), Error, "fractional amount rejected");
assert.throws(() => groupTotals([{ g: "a", n: "3" }], "g", "n"), Error, "string amount rejected");
console.log("ok");
