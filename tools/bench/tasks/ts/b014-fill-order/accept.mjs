import assert from "node:assert/strict";
import { fillOrder } from "./solution.ts";

assert.deepEqual(
  fillOrder([[5, 3]], 3),
  { cost: 15, taken: [3], leftover: [0] },
  "one source drained exactly",
);
assert.deepEqual(
  fillOrder([[5, 10]], 4),
  { cost: 20, taken: [4], leftover: [6] },
  "the draw stops at the need",
);
assert.deepEqual(
  fillOrder([[9, 5], [2, 3]], 4),
  { cost: 15, taken: [1, 3], leftover: [4, 0] },
  "the cheapest source drains first",
);
assert.deepEqual(
  fillOrder([[4, 2], [4, 5]], 3),
  { cost: 12, taken: [2, 1], leftover: [0, 4] },
  "a cost tie goes to the earlier source",
);
assert.deepEqual(
  fillOrder([[3, 2], [7, 2]], 4),
  { cost: 20, taken: [2, 2], leftover: [0, 0] },
  "the order may drain every source",
);
assert.deepEqual(
  fillOrder([[6, 2], [1, 2], [4, 2]], 5),
  { cost: 16, taken: [1, 2, 2], leftover: [1, 0, 0] },
  "three sources drain by rising price",
);
assert.deepEqual(
  fillOrder([[2, 9], [5, 1]], 6),
  { cost: 12, taken: [6, 0], leftover: [3, 1] },
  "an untouched source reads zero taken",
);
assert.deepEqual(
  fillOrder([[8, 1]], 1),
  { cost: 8, taken: [1], leftover: [0] },
  "a single unit order",
);
assert.throws(() => fillOrder([[2, 1]], 5), Error, "stock cannot cover the order");
assert.throws(() => fillOrder([[2, 1]], 0), Error, "zero needed is rejected");
assert.throws(() => fillOrder([[2, 1]], 2.5), Error, "fractional needed");
assert.throws(() => fillOrder([[0, 4]], 1), Error, "zero cost is rejected");
assert.throws(() => fillOrder([[2, -1]], 1), Error, "negative stock is rejected");
assert.throws(() => fillOrder([[2]], 1), Error, "a lone-element source");
console.log("ok");
