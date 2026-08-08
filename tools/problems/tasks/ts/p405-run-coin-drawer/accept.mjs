import assert from "node:assert/strict";
import { runCoinDrawer } from "./solution.ts";

const kiosk = [
  [100, 2],
  [50, 1],
  [20, 3],
  [10, 1],
];

assert.deepEqual(
  runCoinDrawer(kiosk, []),
  {
    till: [
      [100, 2],
      [50, 1],
      [20, 3],
      [10, 1],
    ],
    turnedAway: [],
    earnings: 0,
  },
  "an empty queue leaves the till alone",
);

assert.deepEqual(
  runCoinDrawer(kiosk, [{ price: 30, paid: [50] }]),
  {
    till: [
      [100, 2],
      [50, 2],
      [20, 2],
      [10, 1],
    ],
    turnedAway: [],
    earnings: 30,
  },
  "one settled purchase",
);

assert.deepEqual(
  runCoinDrawer(kiosk, [
    { price: 30, paid: [50] },
    { price: 45, paid: [100] },
    { price: 100, paid: [50, 50] },
    { price: 60, paid: [50] },
  ]),
  {
    till: [
      [100, 2],
      [50, 4],
      [20, 2],
      [10, 1],
    ],
    turnedAway: [1, 3],
    earnings: 130,
  },
  "two turned away and the till rolled back each time",
);

assert.deepEqual(
  runCoinDrawer(
    [
      [25, 0],
      [10, 0],
      [5, 1],
    ],
    [{ price: 20, paid: [25, 10] }],
  ),
  {
    till: [
      [25, 1],
      [10, 0],
      [5, 0],
    ],
    turnedAway: [],
    earnings: 20,
  },
  "the pushed coins are available as change",
);

assert.deepEqual(
  runCoinDrawer(
    [
      [6, 1],
      [4, 2],
    ],
    [{ price: 2, paid: [6, 4] }],
  ),
  {
    till: [
      [6, 1],
      [4, 2],
    ],
    turnedAway: [0],
    earnings: 0,
  },
  "the biggest-first walk may strand a balance a cleverer split would clear",
);

assert.deepEqual(
  runCoinDrawer(
    [
      [10, 1],
      [50, 2],
      [20, 0],
    ],
    [{ price: 40, paid: [50] }],
  ),
  {
    till: [
      [50, 3],
      [20, 0],
      [10, 0],
    ],
    turnedAway: [],
    earnings: 40,
  },
  "an unsorted till is reported biggest first",
);

assert.throws(() => runCoinDrawer(7, []), Error, "a till that is not a list");
assert.throws(() => runCoinDrawer([], []), Error, "a till of no denominations");
assert.throws(() => runCoinDrawer([[10]], []), Error, "a till entry that is not a pair");
assert.throws(() => runCoinDrawer([[0, 3]], []), Error, "a denomination of nothing");
assert.throws(() => runCoinDrawer([[10, -1]], []), Error, "a negative count");
assert.throws(
  () =>
    runCoinDrawer(
      [
        [10, 1],
        [10, 2],
      ],
      [],
    ),
  Error,
  "a denomination listed twice",
);
assert.throws(() => runCoinDrawer(kiosk, 3), Error, "a queue that is not a list");
assert.throws(() => runCoinDrawer(kiosk, [5]), Error, "a purchase that is not a record");
assert.throws(
  () => runCoinDrawer(kiosk, [{ price: 0, paid: [10] }]),
  Error,
  "a price of nothing",
);
assert.throws(
  () => runCoinDrawer(kiosk, [{ price: 1.5, paid: [10] }]),
  Error,
  "a fractional price",
);
assert.throws(() => runCoinDrawer(kiosk, [{ price: 10, paid: 10 }]), Error, "coins not a list");
assert.throws(
  () => runCoinDrawer(kiosk, [{ price: 10, paid: [3] }]),
  Error,
  "a coin the till does not handle",
);
console.log("ok");
