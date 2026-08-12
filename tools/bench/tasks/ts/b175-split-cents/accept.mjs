import assert from "node:assert/strict";
import { splitCents } from "./solution.ts";

assert.deepEqual(splitCents(100, [1, 1]), [50, 50], "an even split leaves nothing over");
assert.deepEqual(splitCents(101, [1, 1]), [51, 50], "the odd cent goes to the earlier partner on a tie");
assert.deepEqual(splitCents(100, [1, 1, 1]), [34, 33, 33], "one cent over three equal partners lands first");
assert.deepEqual(splitCents(5, [3, 1]), [4, 1], "the larger weight takes the leftover cent");
assert.deepEqual(splitCents(7, [1, 1, 1, 1]), [2, 2, 2, 1], "three leftover cents fill the first three partners");
assert.deepEqual(splitCents(0, [3, 1]), [0, 0], "no takings share out as nothing each");
assert.deepEqual(splitCents(99, [5]), [99], "a lone partner takes the whole takings");
assert.throws(() => splitCents(10.5, [1, 1]), Error, "a total that is not whole cents is rejected");
assert.throws(() => splitCents(-5, [1, 1]), Error, "a negative total is rejected");
assert.throws(() => splitCents(10, "1,1"), Error, "weights that are not a list are rejected");
assert.throws(() => splitCents(10, []), Error, "an empty weights list is rejected");
assert.throws(() => splitCents(10, [1, 0]), Error, "a weight that is not positive is rejected");
console.log("ok");
