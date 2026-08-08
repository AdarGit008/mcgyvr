import assert from "node:assert/strict";
import { slideSessions } from "./solution.ts";

const ask = (id, want, span) => ({ id, want, span });

assert.deepEqual(slideSessions([], 0, 60), [], "an empty day books nothing");
assert.deepEqual(
  slideSessions([ask("a", 0, 5), ask("b", 10, 4)], 0, 100),
  ["a 0", "b 10"],
  "requests that never meet keep the moments they wanted",
);
assert.deepEqual(
  slideSessions([ask("a", 0, 5), ask("b", 0, 5)], 0, 100),
  ["a 0", "b 5"],
  "a wanted moment already taken slides to the next free one",
);
assert.deepEqual(
  slideSessions([ask("a", -5, 3)], 0, 10),
  ["a 0"],
  "a want before opening is lifted to the opening moment",
);
assert.deepEqual(
  slideSessions([ask("a", 7, 3)], 0, 10),
  ["a 7"],
  "a session finishing exactly at closing is granted",
);
assert.deepEqual(
  slideSessions([ask("a", 0, 5)], 0, 4),
  ["a away"],
  "a session too long for the day is turned away",
);
assert.deepEqual(
  slideSessions([ask("a", 0, 10), ask("b", 20, 5), ask("c", 5, 3)], 0, 100),
  ["a 0", "b 20", "c 10"],
  "a late request settles in the gap it fits, not after the newest booking",
);
assert.deepEqual(
  slideSessions([ask("a", 0, 10), ask("b", 15, 5), ask("c", 10, 5)], 0, 100),
  ["a 0", "b 15", "c 10"],
  "a gap that fits exactly between two bookings is used",
);
assert.deepEqual(
  slideSessions([ask("a", 0, 50), ask("b", 0, 60), ask("c", 0, 10)], 0, 60),
  ["a 0", "b away", "c 50"],
  "a turned-away request leaves the day untouched for the next one",
);
assert.throws(
  () => slideSessions([], 40, 40),
  Error,
  "a day that shuts when it opens is rejected",
);
assert.throws(
  () => slideSessions([ask("a", 0, 0)], 0, 10),
  Error,
  "a span below one is rejected",
);
assert.throws(
  () => slideSessions([ask("a", 0, 2), ask("a", 5, 2)], 0, 10),
  Error,
  "a repeated id is rejected",
);
assert.throws(
  () => slideSessions([ask("a", "3", 2)], 0, 10),
  Error,
  "a want that is not an integer is rejected",
);
console.log("ok");
