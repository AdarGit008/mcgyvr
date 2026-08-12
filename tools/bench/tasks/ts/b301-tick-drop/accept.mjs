import assert from "node:assert/strict";
import { everyOther } from "./solution.ts";

assert.deepEqual(everyOther(["a", "b", "c"]), ["a", "c"], "the first and the third");
assert.deepEqual(everyOther(["a", "b", "c", "d"]), ["a", "c"], "an even-length log");
assert.deepEqual(everyOther(["a"]), ["a"], "one entry comes back");
assert.deepEqual(everyOther([]), [], "an empty log");
assert.deepEqual(everyOther(["a", "b"]), ["a"], "only the first of a pair");
assert.deepEqual(
  everyOther(["p", "q", "r", "s", "t"]),
  ["p", "r", "t"],
  "three from five",
);
console.log("ok");
