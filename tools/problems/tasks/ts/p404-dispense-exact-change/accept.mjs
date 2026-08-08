import assert from "node:assert/strict";
import { dispenseExactChange } from "./solution.ts";

const till = [
  [25, 4],
  [10, 3],
  [5, 2],
  [1, 10],
];

assert.deepEqual(dispenseExactChange(0, till), [], "nothing owed pays nothing");
assert.deepEqual(dispenseExactChange(3, till), [[1, 3]], "smallest face only");
assert.deepEqual(
  dispenseExactChange(8, till),
  [
    [5, 1],
    [1, 3],
  ],
  "two faces",
);
assert.deepEqual(
  dispenseExactChange(30, till),
  [
    [25, 1],
    [5, 1],
  ],
  "fewest coins beats the obvious tens",
);
assert.deepEqual(
  dispenseExactChange(40, till),
  [
    [25, 1],
    [10, 1],
    [5, 1],
  ],
  "three faces",
);
assert.deepEqual(
  dispenseExactChange(60, till),
  [
    [25, 2],
    [10, 1],
  ],
  "repeated largest face",
);
assert.deepEqual(dispenseExactChange(100, till), [[25, 4]], "the whole stock of one face");

const scarce = [
  [25, 1],
  [10, 0],
  [5, 3],
];
assert.deepEqual(dispenseExactChange(15, scarce), [[5, 3]], "an empty stock is unusable");
assert.deepEqual(
  dispenseExactChange(35, scarce),
  [
    [25, 1],
    [5, 2],
  ],
  "the stocked faces carry it",
);

const tied = [
  [5, 2],
  [3, 5],
  [2, 5],
  [1, 10],
];
assert.deepEqual(
  dispenseExactChange(6, tied),
  [
    [5, 1],
    [1, 1],
  ],
  "a tie on coins goes to the larger face",
);

const odd = [
  [9, 1],
  [6, 2],
  [5, 1],
  [4, 1],
  [1, 3],
];
assert.deepEqual(
  dispenseExactChange(10, odd),
  [
    [9, 1],
    [1, 1],
  ],
  "the greedy face wins a genuine tie",
);
assert.deepEqual(dispenseExactChange(12, odd), [[6, 2]], "greedy would fail here");

assert.throws(() => dispenseExactChange(200, till), Error, "beyond the stock is refused");
assert.throws(() => dispenseExactChange(7, [[5, 10]]), Error, "no exact combination");
assert.throws(() => dispenseExactChange(-1, till), Error, "a negative amount is refused");
assert.throws(() => dispenseExactChange(2.5, till), Error, "a fractional amount is refused");
assert.throws(() => dispenseExactChange("10", till), Error, "a non-number amount is refused");
assert.throws(() => dispenseExactChange(100001, till), Error, "an amount over the ceiling");
assert.throws(() => dispenseExactChange(5, 5), Error, "a hopper that is not a list");
assert.throws(() => dispenseExactChange(5, []), Error, "a hopper with no faces");
assert.throws(() => dispenseExactChange(5, [[25]]), Error, "an entry that is not a pair");
assert.throws(() => dispenseExactChange(5, [[0, 3]]), Error, "a face value of nothing");
assert.throws(() => dispenseExactChange(5, [[2.5, 3]]), Error, "a fractional face value");
assert.throws(() => dispenseExactChange(5, [[5, -1]]), Error, "a negative stock");
assert.throws(
  () =>
    dispenseExactChange(5, [
      [5, 1],
      [5, 2],
    ]),
  Error,
  "one face listed twice",
);
console.log("ok");
