import assert from "node:assert/strict";
import { truncatedProduct } from "./solution.ts";

assert.deepEqual(truncatedProduct([1, 2], [1, 3], 5), [1, 5, 6], "plain product");
assert.deepEqual(truncatedProduct([3], [4], 0), [12], "two constants");
assert.deepEqual(
  truncatedProduct([2, -3, 1], [1, 1], 10),
  [2, -1, -2, 1],
  "cap above the degree",
);
assert.deepEqual(
  truncatedProduct([1, -1], [1, 1, 1, 1], 4),
  [1, 0, 0, 0, -1],
  "interior zeros survive",
);
assert.deepEqual(
  truncatedProduct([1, -1], [1, 1, 1, 1], 3),
  [1],
  "cutting the top term strips the zeros under it",
);
assert.deepEqual(truncatedProduct([1, -1], [1, 1], 1), [1], "cut to a constant");
assert.deepEqual(truncatedProduct([0, 1], [0, 1], 2), [0, 0, 1], "shifted squares");
assert.deepEqual(truncatedProduct([0, 1], [0, 1], 1), [], "cut away to nothing");
assert.deepEqual(truncatedProduct([], [1, 2], 3), [], "zero times anything");
assert.deepEqual(truncatedProduct([1, 1], [1, 1], 0), [1], "cap zero keeps the constant");

assert.throws(() => truncatedProduct([1, 0], [1], 2), Error, "trailing zero rejected");
assert.throws(() => truncatedProduct([1], [0], 2), Error, "bare zero rejected");
assert.throws(() => truncatedProduct([1, 1.5], [1], 2), Error, "fraction rejected");
assert.throws(() => truncatedProduct("x", [1], 2), Error, "non-list rejected");
assert.throws(() => truncatedProduct([1], [1], -1), Error, "negative cap rejected");
assert.throws(() => truncatedProduct([1], [1], 1.5), Error, "fractional cap rejected");
console.log("ok");
