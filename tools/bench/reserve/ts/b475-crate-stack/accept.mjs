import assert from "node:assert/strict";
import { crateStack } from "./solution.ts";

assert.deepEqual(crateStack(["short", "short", "tall"], 9), ["short", "short", "tall"], "the pile reaches the ceiling exactly");
assert.deepEqual(crateStack(["tall", "tall"], 9), ["tall"], "the second would pass the ceiling");
assert.deepEqual(crateStack(["tall", "short", "short"], 7), ["tall", "short"], "stopping part way");
assert.deepEqual(crateStack(["odd", "short"], 5), ["odd", "short"], "an unnamed kind takes the middle height");
assert.deepEqual(crateStack(["short"], 1), [], "the first crate already passes it");
assert.deepEqual(crateStack([], 5), [], "an empty run");
console.log("ok");
