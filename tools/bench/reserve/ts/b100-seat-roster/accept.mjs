import assert from "node:assert/strict";
import { normalizeSeats } from "./solution.ts";

assert.deepEqual(normalizeSeats(["B12"]), ["B12"], "a plain seat passes through");
assert.deepEqual(normalizeSeats(["b-12"]), ["B12"], "case and hyphen normalize away");
assert.deepEqual(normalizeSeats([" c007 "]), ["C7"], "padding and leading zeros strip");
assert.deepEqual(
  normalizeSeats(["J4", "A1", "e-9"]),
  ["J4", "A1", "E9"],
  "input order is kept",
);
assert.deepEqual(normalizeSeats([]), [], "an empty booking stays empty");
assert.throws(() => normalizeSeats("B7"), Error, "a non-list argument is rejected");
assert.throws(() => normalizeSeats([7]), Error, "a non-string entry is rejected");
assert.throws(() => normalizeSeats([" "]), Error, "a blank entry is rejected");
assert.throws(() => normalizeSeats(["12"]), Error, "a missing row letter is rejected");
assert.throws(() => normalizeSeats(["B12x"]), Error, "trailing junk is rejected");
assert.throws(() => normalizeSeats(["B000"]), Error, "seat zero is rejected");
assert.throws(() => normalizeSeats(["B7", "b-07"]), Error, "a duplicate seat is rejected");
console.log("ok");
