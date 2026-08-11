import assert from "node:assert/strict";
import { runPress } from "./solution.ts";

assert.deepEqual(runPress([["flyer", 2], ["poster", 3]], 10), { printed: ["flyer", "poster"], waiting: [], pages: 5 }, "a queue that fits prints whole");
assert.deepEqual(runPress([["memo", 4], ["book", 5], ["card", 1]], 6), { printed: ["memo"], waiting: ["book", "card"], pages: 4 }, "the first misfit stops serving even when a later job would fit");
assert.deepEqual(runPress([["memo", 3], ["card", 3]], 6), { printed: ["memo", "card"], waiting: [], pages: 6 }, "an exact fit spends the whole budget");
assert.deepEqual(runPress([["book", 7]], 6), { printed: [], waiting: ["book"], pages: 0 }, "a first job too big prints nothing");
assert.deepEqual(runPress([["card", 1]], 0), { printed: [], waiting: ["card"], pages: 0 }, "a zero budget serves nobody");
assert.deepEqual(runPress([], 4), { printed: [], waiting: [], pages: 0 }, "an empty queue spends nothing");
assert.throws(() => runPress(42, 5), Error, "a non-list queue is rejected");
assert.throws(() => runPress([["solo"]], 5), Error, "a job that is not a pair is rejected");
assert.throws(() => runPress([["", 2]], 5), Error, "an empty job name is rejected");
assert.throws(() => runPress([["big", 9], ["late", 0]], 5), Error, "a bad page count is rejected even past the stopping point");
assert.throws(() => runPress([["card", 1]], -1), Error, "a negative budget is rejected");
console.log("ok");
