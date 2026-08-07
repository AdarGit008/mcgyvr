import assert from "node:assert/strict";
import { settleSwapRequests } from "./solution.ts";

const duty = (day, post, worker) => ({ day, post, worker });
const swap = (left, right) => ({ left, right });

const depot = () => ({
  duties: [
    duty(1, "gate", "ana"),
    duty(2, "dock", "bo"),
    duty(3, "gate", "cy"),
    duty(4, "dock", "ana"),
    duty(2, "gate", "dee"),
    duty(5, "dock", "bo"),
  ],
  cleared: [
    { worker: "ana", posts: ["gate", "dock"] },
    { worker: "bo", posts: ["gate", "dock"] },
    { worker: "cy", posts: ["gate"] },
    { worker: "dee", posts: ["gate", "dock"] },
  ],
  peak: [2, 4],
  cap: 1,
  quota: 1,
});

assert.deepEqual(
  settleSwapRequests(depot(), [
    swap([1, "gate"], [3, "gate"]),
    swap([3, "gate"], [2, "dock"]),
    swap([2, "gate"], [2, "dock"]),
    swap([1, "gate"], [2, "gate"]),
    swap([9, "gate"], [1, "gate"]),
    swap([4, "dock"], [4, "dock"]),
    swap([3, "gate"], [4, "dock"]),
    swap([1, "gate"], [2, "dock"]),
    swap([5, "dock"], [2, "dock"]),
  ]),
  {
    rulings: [
      "taken",
      "peak",
      "taken",
      "quota",
      "unknown",
      "same",
      "same",
      "uncleared",
      "clash",
    ],
    roster: [
      "1 gate cy",
      "2 dock dee",
      "2 gate bo",
      "3 gate ana",
      "4 dock ana",
      "5 dock bo",
    ],
  },
  "every refusal reason and two grants over one board",
);

assert.deepEqual(
  settleSwapRequests(depot(), []),
  {
    rulings: [],
    roster: [
      "1 gate ana",
      "2 dock bo",
      "2 gate dee",
      "3 gate cy",
      "4 dock ana",
      "5 dock bo",
    ],
  },
  "no requests leaves the board as it opened",
);

assert.deepEqual(
  settleSwapRequests({ ...depot(), quota: 0 }, [swap([1, "gate"], [3, "gate"])]),
  {
    rulings: ["quota"],
    roster: [
      "1 gate ana",
      "2 dock bo",
      "2 gate dee",
      "3 gate cy",
      "4 dock ana",
      "5 dock bo",
    ],
  },
  "a quota of nought grants nothing",
);

assert.deepEqual(
  settleSwapRequests({ ...depot(), peak: [], cap: 0, quota: 5 }, [
    swap([2, "dock"], [4, "dock"]),
  ]),
  {
    rulings: ["taken"],
    roster: [
      "1 gate ana",
      "2 dock ana",
      "2 gate dee",
      "3 gate cy",
      "4 dock bo",
      "5 dock bo",
    ],
  },
  "with no peak days the cap never bites",
);

assert.deepEqual(
  settleSwapRequests(
    {
      duties: [duty(1, "a", "pat"), duty(1, "b", "quin")],
      cleared: [
        { worker: "pat", posts: ["a", "b"] },
        { worker: "quin", posts: ["a", "b"] },
      ],
      peak: [],
      cap: 0,
      quota: 4,
    },
    [swap([1, "a"], [1, "b"]), swap([1, "a"], [1, "b"])],
  ),
  { rulings: ["taken", "taken"], roster: ["1 a pat", "1 b quin"] },
  "two grants in a row put the board back where it began",
);

assert.throws(() => settleSwapRequests("no", []), Error, "the board must be a record");
assert.throws(
  () => settleSwapRequests({ duties: [], cleared: [], peak: [], cap: 0 }, []),
  Error,
  "a missing board key is refused",
);
assert.throws(
  () => settleSwapRequests({ ...depot(), duties: [duty(0, "a", "pat")] }, []),
  Error,
  "a day of nought is refused",
);
assert.throws(
  () =>
    settleSwapRequests(
      { ...depot(), duties: [duty(1, "a", "pat"), duty(1, "a", "quin")] },
      [],
    ),
  Error,
  "two duties on one day and post are refused",
);
assert.throws(
  () =>
    settleSwapRequests(
      {
        duties: [duty(1, "a", "pat"), duty(1, "b", "pat")],
        cleared: [{ worker: "pat", posts: ["a", "b"] }],
        peak: [],
        cap: 0,
        quota: 1,
      },
      [],
    ),
  Error,
  "a worker opening on two posts of one day is refused",
);
assert.throws(
  () => settleSwapRequests({ ...depot(), cleared: [{ worker: "ana", posts: ["gate"] }] }, []),
  Error,
  "a worker with no clearance is refused",
);
assert.throws(
  () => settleSwapRequests({ ...depot(), peak: [2, 2] }, []),
  Error,
  "a repeated peak day is refused",
);
assert.throws(
  () => settleSwapRequests({ ...depot(), cap: -1 }, []),
  Error,
  "a negative cap is refused",
);
assert.throws(() => settleSwapRequests(depot(), "no"), Error, "requests must be a list");
assert.throws(
  () => settleSwapRequests(depot(), [{ left: [1, "gate"] }]),
  Error,
  "a request missing a side is refused",
);
assert.throws(
  () => settleSwapRequests(depot(), [swap([1, "gate"], [2])]),
  Error,
  "a one-entry side is refused",
);
assert.throws(
  () => settleSwapRequests(depot(), [swap([1, "gate"], [2, ""])]),
  Error,
  "an empty post on a side is refused",
);
console.log("ok");
