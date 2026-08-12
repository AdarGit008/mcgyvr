import assert from "node:assert/strict";
import { splitAt } from "./solution.ts";

assert.deepEqual(splitAt(["a", "x", "b"], "x"), [["a"], ["b"]], "broken at the marker");
assert.deepEqual(splitAt(["a"], "x"), [["a"], []], "the marker is absent");
assert.deepEqual(splitAt([], "x"), [[], []], "an empty list");
assert.deepEqual(splitAt(["x"], "x"), [[], []], "the marker is all there is");
assert.deepEqual(splitAt(["x", "a"], "x"), [[], ["a"]], "the marker leads");
assert.deepEqual(
  splitAt(["a", "x", "b", "x"], "x"),
  [["a"], ["b", "x"]],
  "only the first marker breaks it",
);
console.log("ok");
