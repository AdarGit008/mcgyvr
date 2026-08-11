import assert from "node:assert/strict";
import { swipeDedupe } from "./solution.ts";

assert.deepEqual(swipeDedupe(["a", "a", "b"]), ["a", "b"], "a repeat is dropped");
assert.deepEqual(swipeDedupe(["a", "b", "a"]), ["a", "b", "a"], "a return is kept");
assert.deepEqual(swipeDedupe(["a"]), ["a"], "a single swipe");
assert.deepEqual(swipeDedupe([]), [], "no swipes at all");
assert.deepEqual(swipeDedupe(["a", "a", "a"]), ["a"], "a long run collapses");
assert.deepEqual(
  swipeDedupe(["a", "b", "b", "a"]),
  ["a", "b", "a"],
  "only adjacent repeats go",
);
console.log("ok");
