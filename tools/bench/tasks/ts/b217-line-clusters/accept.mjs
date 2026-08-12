import assert from "node:assert/strict";
import { lineClusters } from "./solution.ts";

assert.deepEqual(lineClusters(["depot", "market", "pier"], [["depot", "market"], ["market", "pier"]]), [["depot", "market", "pier"]], "segments in a run join every stop they touch");
assert.deepEqual(lineClusters(["north", "south", "east", "west"], [["north", "south"], ["east", "west"]]), [["east", "west"], ["north", "south"]], "separate runs stay apart and lead with their first stop");
assert.deepEqual(lineClusters(["quay", "mill", "yard"], [["mill", "yard"]]), [["mill", "yard"], ["quay"]], "a stop no segment touches forms its own cluster");
assert.deepEqual(lineClusters(["zoo", "arch", "kiln"], [["zoo", "kiln"], ["kiln", "arch"]]), [["arch", "kiln", "zoo"]], "a cluster lists its stops alphabetically, not as served");
assert.deepEqual(lineClusters([], []), [], "an operator serving no stops has no clusters");
assert.deepEqual(lineClusters(["alpha", "beta"], [["alpha", "beta"], ["beta", "alpha"], ["alpha", "beta"]]), [["alpha", "beta"]], "a segment listed again changes nothing");
console.log("ok");
