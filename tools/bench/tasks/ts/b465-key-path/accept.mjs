import assert from "node:assert/strict";
import { keyPath } from "./solution.ts";

assert.deepEqual(keyPath({ "a.b": "1" }, "a"), ["b"], "one name under the head");
assert.deepEqual(keyPath({ "a.b.c": "1" }, "a"), [], "a deeper name is left out");
assert.deepEqual(keyPath({ b: "1" }, "a"), [], "nothing is under the head");
assert.deepEqual(keyPath({}, "a"), [], "an empty store");
assert.deepEqual(
  keyPath({ "a.b": "1", "a.c": "2" }, "a"),
  ["b", "c"],
  "two names under one head",
);
assert.deepEqual(keyPath({ "a.b": "1", "x.y": "2" }, "x"), ["y"], "a different head");
console.log("ok");
