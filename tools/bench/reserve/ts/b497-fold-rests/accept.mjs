import assert from "node:assert/strict";
import { foldRests } from "./solution.ts";

assert.deepEqual(foldRests(["a", "", "", "b"]), ["a", "-", "b"], "a stretch of rests folds to one dash");
assert.deepEqual(foldRests(["a", " ", "b", "", "c"]), ["a", "-", "b", "-", "c"], "two stretches stand apart");
assert.deepEqual(foldRests(["", "a"]), ["-", "a"], "a run opening on a rest");
assert.deepEqual(foldRests(["a", "b"]), ["a", "b"], "a run holding no rests");
assert.deepEqual(foldRests(["a", "  "]), ["a", "-"], "blank space counts as a rest");
assert.deepEqual(foldRests([]), [], "a run holding nothing");
console.log("ok");
