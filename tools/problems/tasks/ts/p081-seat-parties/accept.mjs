import assert from "node:assert/strict";
import { seatParties } from "./solution.ts";

assert.deepEqual(seatParties([4, 6], []), [], "no parties, no records");

assert.deepEqual(
  seatParties([4, 6], [2, 2]),
  ["1-1", "1-3"],
  "seats advance within a row"
);

assert.deepEqual(
  seatParties([4, 6], [3, 2, 1]),
  ["1-1", "2-1", "1-4"],
  "a party too wide for row one spills to row two"
);

assert.deepEqual(
  seatParties([3, 3], [3, 3, 1]),
  ["1-1", "2-1", "rejected:full"],
  "a filled hall rejects with full"
);

assert.deepEqual(
  seatParties([3, 5], [6]),
  ["rejected:too_big"],
  "a party longer than the longest row is too_big"
);

assert.deepEqual(
  seatParties([3, 3], [3, 3, 3, 4]),
  ["1-1", "2-1", "rejected:full", "rejected:too_big"],
  "full and too_big are distinguished"
);

assert.deepEqual(
  seatParties([3], [2, 2, 1]),
  ["1-1", "rejected:full", "1-3"],
  "a rejected party occupies nothing and later parties still seat"
);

assert.throws(() => seatParties([3], [0]), Error, "size zero is an error");

console.log("ok");
