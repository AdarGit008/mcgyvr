import assert from "node:assert/strict";
import { planRoomMoves } from "./solution.ts";

const book = (id, start, end, fixed = false) => ({ id, start, end, fixed });

assert.deepEqual(planRoomMoves([]), [], "an empty diary needs no moves");
assert.deepEqual(
  planRoomMoves([book("a", 0, 10), book("b", 10, 20)]),
  [],
  "touching half-open spans do not clash",
);
assert.deepEqual(
  planRoomMoves([book("a", 0, 30), book("b", 5, 10), book("c", 12, 18)]),
  ["a"],
  "one long booking yields to two short ones",
);
assert.deepEqual(
  planRoomMoves([book("b", 0, 10), book("a", 2, 10)]),
  ["a"],
  "equal ends are settled by the earlier start",
);
assert.deepEqual(
  planRoomMoves([
    book("p", 10, 20, true),
    book("q", 15, 25),
    book("r", 0, 5),
    book("s", 20, 30),
  ]),
  ["q"],
  "a movable booking overlapping a nailed one always goes",
);
assert.deepEqual(
  planRoomMoves([book("p", 0, 10, true), book("q", 20, 30, true), book("m", 5, 25)]),
  ["m"],
  "a booking straddling two nailed ones goes",
);
assert.deepEqual(
  planRoomMoves([
    book("w", 0, 4, true),
    book("x", 4, 12),
    book("y", 5, 8),
    book("z", 9, 11),
  ]),
  ["x"],
  "the gap after a nailed booking still takes the two-booking answer",
);
assert.deepEqual(
  planRoomMoves([book("g", 6, 9), book("h", 0, 7), book("i", 8, 14)]),
  ["g"],
  "the greedy walk keeps the pair that fits, not the first seen",
);
assert.deepEqual(
  planRoomMoves([book("p", 10, 20, true), book("q", 12, 14), book("r", 0, 30)]),
  ["r", "q"],
  "moved ids come back ordered by start, not by discovery",
);
assert.throws(
  () => planRoomMoves([book("p", 0, 10, true), book("q", 5, 15, true)]),
  Error,
  "two overlapping nailed bookings are beyond repair",
);
assert.throws(
  () => planRoomMoves([book("a", 7, 7)]),
  Error,
  "a span of no length is rejected",
);
assert.throws(
  () => planRoomMoves([book("a", 0, 5), book("a", 6, 9)]),
  Error,
  "a repeated id is rejected",
);
assert.throws(
  () => planRoomMoves([{ id: "a", start: 0, end: 5 }]),
  Error,
  "a missing fixed flag is rejected",
);
assert.throws(
  () => planRoomMoves([book("", 0, 5)]),
  Error,
  "an empty id is rejected",
);
console.log("ok");
