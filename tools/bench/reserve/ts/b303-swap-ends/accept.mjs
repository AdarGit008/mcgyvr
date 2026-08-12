import assert from "node:assert/strict";
import { swapEnds } from "./solution.ts";

assert.deepEqual(swapEnds(["a", "b", "c"]), ["c", "b", "a"], "the ends trade places");
assert.deepEqual(swapEnds(["a", "b"]), ["b", "a"], "a pair is all ends");
assert.deepEqual(swapEnds(["a"]), ["a"], "one entry is unchanged");
assert.deepEqual(swapEnds([]), [], "an empty list");
assert.deepEqual(
  swapEnds(["x", "y", "z", "w"]),
  ["w", "y", "z", "x"],
  "the middle stays put",
);

const source = ["a", "b", "c"];
swapEnds(source);
assert.deepEqual(source, ["a", "b", "c"], "the caller's list is left alone");
console.log("ok");
