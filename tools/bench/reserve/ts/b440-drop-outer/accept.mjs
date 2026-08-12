import assert from "node:assert/strict";
import { dropOuter } from "./solution.ts";

assert.deepEqual(dropOuter(["a", "b", "c"]), ["b"], "the middle survives");
assert.deepEqual(dropOuter(["a", "b"]), [], "two entries are both ends");
assert.deepEqual(dropOuter(["a"]), [], "one entry");
assert.deepEqual(dropOuter([]), [], "no entries at all");
assert.deepEqual(dropOuter(["a", "b", "c", "d"]), ["b", "c"], "two survive");
assert.deepEqual(dropOuter(["w", "x", "y", "z", "0"]), ["x", "y", "z"], "three survive");
console.log("ok");
