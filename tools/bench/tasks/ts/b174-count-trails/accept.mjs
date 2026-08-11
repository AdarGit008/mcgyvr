import assert from "node:assert/strict";
import { countTrails } from "./solution.ts";

assert.equal(countTrails(1, 1, []), 1, "a single cell is crossed one way");
assert.equal(countTrails(1, 5, []), 1, "a single row leaves one route");
assert.equal(countTrails(2, 2, []), 2, "a two by two floor has two routes");
assert.equal(countTrails(3, 3, []), 6, "an open three by three floor has six routes");
assert.equal(countTrails(3, 3, [[1, 1]]), 2, "a rope in the middle cuts the routes to two");
assert.equal(countTrails(2, 2, [[0, 1], [1, 0]]), 0, "ropes across both middles leave no route");
assert.equal(countTrails(4, 3, [[1, 1]]), 4, "one rope on a taller floor leaves four routes");
assert.throws(() => countTrails(0, 3, []), Error, "a floor with no rows is rejected");
assert.throws(() => countTrails(2, 2, [[1]]), Error, "a roped entry of one number is rejected");
assert.throws(() => countTrails(2, 2, [[2, 0]]), Error, "a roped cell off the floor is rejected");
assert.throws(() => countTrails(2, 2, [[0, 0]]), Error, "a rope across the entrance is rejected");
console.log("ok");
