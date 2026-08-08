import assert from "node:assert/strict";
import { runPourScript } from "./solution.ts";

assert.deepEqual(runPourScript([3, 5], []), [0, 0], "an empty script changes nothing");
assert.deepEqual(runPourScript([3, 5], ["fill A"]), [3, 0], "a fill tops one flask");
assert.deepEqual(
  runPourScript([3, 5], ["fill B", "pour B A"]),
  [3, 2],
  "a pour into a dry flask stops at its capacity",
);
assert.deepEqual(
  runPourScript([3, 5], ["fill A", "fill B", "pour A B"]),
  [3, 5],
  "a brimming receiver takes nothing",
);
assert.deepEqual(
  runPourScript([3, 5], ["fill B", "pour B A", "empty A"]),
  [0, 2],
  "an empty leaves the rest untouched",
);
assert.deepEqual(
  runPourScript([4, 3, 2], ["fill A", "fill C", "pour A C"]),
  [4, 0, 2],
  "a full receiver blocks the whole transfer",
);
assert.deepEqual(
  runPourScript([4, 3, 2], ["fill A", "pour A B", "pour B C"]),
  [1, 1, 2],
  "a chain of pours down the rack",
);
assert.throws(() => runPourScript([3, 5], ["tip A"]), Error, "unknown action");
assert.throws(() => runPourScript([3, 5], ["fill Z"]), Error, "mark past the rack");
assert.throws(() => runPourScript([3, 5], ["pour A A"]), Error, "pour into itself");
assert.throws(() => runPourScript([3, 5], ["fill"]), Error, "too few words");
assert.throws(() => runPourScript([3, 5], ["pour A B C"]), Error, "too many words");
assert.throws(() => runPourScript([3, 5], [7]), Error, "a line that is not a string");
assert.throws(() => runPourScript([], ["fill A"]), Error, "an empty rack");
console.log("ok");
