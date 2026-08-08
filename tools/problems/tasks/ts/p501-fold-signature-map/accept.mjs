import assert from "node:assert/strict";
import { foldSignatureMap } from "./solution.ts";

assert.deepEqual(
  foldSignatureMap(20, 8, [1, 2, 5, 8, 9, 16, 20]),
  [
    "1 1 1 front right",
    "2 1 1 back left",
    "5 1 2 back right",
    "8 1 1 front left",
    "9 2 1 front right",
    "16 2 1 front left",
    "20 3 2 back left",
  ],
  "eight-page signatures across three gatherings",
);

assert.deepEqual(
  foldSignatureMap(10, 4, [1, 2, 3, 4, 5, 9, 10]),
  [
    "1 1 1 front right",
    "2 1 1 back left",
    "3 1 1 back right",
    "4 1 1 front left",
    "5 2 1 front right",
    "9 3 1 front right",
    "10 3 1 back left",
  ],
  "four-page signatures put all four places on one sheet",
);

assert.deepEqual(
  foldSignatureMap(64, 16, [1, 8, 9, 16, 17, 32]),
  [
    "1 1 1 front right",
    "8 1 4 back left",
    "9 1 4 back right",
    "16 1 1 front left",
    "17 2 1 front right",
    "32 2 1 front left",
  ],
  "sixteen-page signatures fold onto four sheets",
);

assert.deepEqual(
  foldSignatureMap(12, 4, [3, 3]),
  ["3 1 1 back right", "3 1 1 back right"],
  "a repeated page is answered twice",
);

assert.deepEqual(foldSignatureMap(12, 4, []), [], "no wanted pages gives no lines");

assert.deepEqual(
  foldSignatureMap(6, 8, [5, 6]),
  ["5 1 2 back right", "6 1 2 front left"],
  "a book padded out short of a whole signature",
);

assert.throws(() => foldSignatureMap(0, 4, [1]), Error, "a page count of nought is refused");
assert.throws(() => foldSignatureMap(20001, 4, [1]), Error, "beyond twenty thousand is refused");
assert.throws(() => foldSignatureMap(20, 6, [1]), Error, "a signature not dividing by four is refused");
assert.throws(() => foldSignatureMap(20, 2, [1]), Error, "a signature below four is refused");
assert.throws(() => foldSignatureMap(20, 404, [1]), Error, "a signature beyond four hundred is refused");
assert.throws(() => foldSignatureMap(20, 4, "no"), Error, "the wanted pages must be a list");
assert.throws(() => foldSignatureMap(20, 4, [0]), Error, "a wanted page of nought is refused");
assert.throws(() => foldSignatureMap(20, 4, [21]), Error, "a wanted page past the book is refused");
assert.throws(() => foldSignatureMap(20, 4, [2.5]), Error, "a fractional wanted page is refused");
console.log("ok");
