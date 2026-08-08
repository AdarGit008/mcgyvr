import assert from "node:assert/strict";
import { firstOverload } from "./solution.ts";

assert.equal(firstOverload([[0, 10], [5, 15]], 1), 5, "two overlapping, capacity one");
assert.equal(firstOverload([[0, 10], [5, 15]], 2), -1, "capacity two absorbs the pair");
assert.equal(firstOverload([[0, 5], [5, 10]], 1), -1, "touching spans never overlap");
assert.equal(firstOverload([[0, 10], [2, 8], [4, 6]], 2), 4, "third joiner overloads");
assert.equal(firstOverload([[5, 15], [0, 10]], 1), 5, "order of input is irrelevant");
assert.equal(firstOverload([], 3), -1, "no bookings never overload");
assert.equal(
  firstOverload([[0, 5], [3, 7], [5, 9]], 2),
  -1,
  "an end at time t frees the slot before a start at t takes it",
);
assert.throws(() => firstOverload([[0, 5]], 0), Error, "zero capacity is rejected");
assert.throws(() => firstOverload([[5, 5]], 1), Error, "empty span is rejected");
assert.throws(() => firstOverload([[4, 2]], 1), Error, "reversed span is rejected");
assert.throws(() => firstOverload([[0, 1.5]], 1), Error, "fractional endpoint");
assert.throws(() => firstOverload("nope", 1), Error, "non-list bookings rejected");
console.log("ok");
