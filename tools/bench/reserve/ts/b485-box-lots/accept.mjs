import assert from "node:assert/strict";
import { boxLots } from "./solution.ts";

assert.deepEqual(boxLots(["a", "b", "c", "d", "e"], 2), [["a", "b"], ["c", "d"], ["e"]], "a closing lot that does not fill");
assert.deepEqual(boxLots(["a", "b", "c", "d"], 2), [["a", "b"], ["c", "d"]], "every lot fills exactly");
assert.deepEqual(boxLots(["a"], 3), [["a"]], "one entry in a lot that never fills");
assert.deepEqual(boxLots(["a", "b", "c"], 1), [["a"], ["b"], ["c"]], "lots of one");
assert.deepEqual(boxLots(["a", "b", "c"], 5), [["a", "b", "c"]], "a size larger than the run");
assert.deepEqual(boxLots([], 2), [], "a run holding nothing");
console.log("ok");
