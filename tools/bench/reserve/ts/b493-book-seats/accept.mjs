import assert from "node:assert/strict";
import { bookSeats } from "./solution.ts";

assert.deepEqual(bookSeats(["a1", "a2", "b1"]), { a: ["a1", "a2"], b: ["b1"] }, "seats gather under their row");
assert.deepEqual(bookSeats(["b2", "a1"]), { b: ["b2"], a: ["a1"] }, "rows appear as they arrive");
assert.deepEqual(bookSeats(["a3"]), { a: ["a3"] }, "a single seat");
assert.deepEqual(bookSeats(["a2", "a1"]), { a: ["a2", "a1"] }, "seats hold their arriving order");
assert.deepEqual(bookSeats([]), {}, "no seats at all");
assert.throws(() => bookSeats(["a1", "a1"]), Error, "a seat booked twice is rejected");
console.log("ok");
