import assert from "node:assert/strict";
import { reserveLots } from "./solution.ts";

const shelf = [["a7", "2026-04-02", 5], ["b2", "2026-03-30", 3], ["c9", "2026-04-02", 4]];
assert.deepEqual(reserveLots(shelf, [["o1", 4], ["o2", 6]]), { picks: [["o1", "b2", 3], ["o1", "a7", 1], ["o2", "a7", 4], ["o2", "c9", 2]], short: [] }, "orders walk the lots from the earliest use-by onward");
assert.deepEqual(reserveLots(shelf, []), { picks: [], short: [] }, "no orders draw nothing");
assert.deepEqual(reserveLots([["x1", "2026-01-05", 2]], [["o1", 5]]), { picks: [["o1", "x1", 2]], short: [["o1", 3]] }, "a part-filled order keeps its draws and records the shortfall");
assert.deepEqual(reserveLots([], [["o1", 1]]), { picks: [], short: [["o1", 1]] }, "an empty shelf is all shortfall");
assert.deepEqual(reserveLots([["z1", "2026-02-01", 1], ["a1", "2026-02-01", 1]], [["o1", 2]]), { picks: [["o1", "a1", 1], ["o1", "z1", 1]], short: [] }, "the smaller lot id wins a tie of dates");
assert.deepEqual(reserveLots([["x1", "2026-01-05", 2]], [["o1", 0]]), { picks: [], short: [] }, "an order for no units draws nothing");
console.log("ok");
