import assert from "node:assert/strict";
import { foldMutualDues } from "./solution.ts";

assert.deepEqual(foldMutualDues([]), [], "no slips fold to nothing");
assert.deepEqual(
  foldMutualDues([{ who: "ivy", whom: "jon", cents: 700 }]),
  [{ who: "ivy", whom: "jon", cents: 700 }],
  "a lone slip survives untouched",
);
assert.deepEqual(
  foldMutualDues([
    { who: "ivy", whom: "jon", cents: 700 },
    { who: "jon", whom: "ivy", cents: 700 },
  ]),
  [],
  "matching directions wipe the pair out",
);
assert.deepEqual(
  foldMutualDues([
    { who: "ivy", whom: "jon", cents: 700 },
    { who: "jon", whom: "ivy", cents: 250 },
  ]),
  [{ who: "ivy", whom: "jon", cents: 450 }],
  "the heavier direction keeps the difference",
);
assert.deepEqual(
  foldMutualDues([
    { who: "ivy", whom: "jon", cents: 250 },
    { who: "jon", whom: "ivy", cents: 700 },
  ]),
  [{ who: "jon", whom: "ivy", cents: 450 }],
  "the surviving slip may point the other way",
);
assert.deepEqual(
  foldMutualDues([
    { who: "ivy", whom: "jon", cents: 100 },
    { who: "ivy", whom: "jon", cents: 50 },
    { who: "jon", whom: "ivy", cents: 30 },
  ]),
  [{ who: "ivy", whom: "jon", cents: 120 }],
  "repeated slips in one direction add up first",
);
assert.deepEqual(
  foldMutualDues([
    { who: "jon", whom: "ivy", cents: 40 },
    { who: "ivy", whom: "kai", cents: 10 },
    { who: "kai", whom: "jon", cents: 5 },
  ]),
  [
    { who: "ivy", whom: "kai", cents: 10 },
    { who: "jon", whom: "ivy", cents: 40 },
    { who: "kai", whom: "jon", cents: 5 },
  ],
  "a ring of three pairs is left as three slips in name order",
);
assert.deepEqual(
  foldMutualDues([
    { who: "ivy", whom: "jon", cents: 50 },
    { who: "jon", whom: "kai", cents: 50 },
  ]),
  [
    { who: "ivy", whom: "jon", cents: 50 },
    { who: "jon", whom: "kai", cents: 50 },
  ],
  "a debt never hops onto a third person",
);

assert.throws(() => foldMutualDues("slips"), Error, "a non-list is rejected");
assert.throws(
  () => foldMutualDues([{ who: "ivy", cents: 5 }]),
  Error,
  "a slip missing whom is rejected",
);
assert.throws(
  () => foldMutualDues([{ who: "ivy", whom: "ivy", cents: 5 }]),
  Error,
  "one person named twice is rejected",
);
assert.throws(
  () => foldMutualDues([{ who: "ivy", whom: "jon", cents: 0 }]),
  Error,
  "cents of zero is rejected",
);
assert.throws(
  () => foldMutualDues([{ who: "ivy", whom: "jon", cents: 1.25 }]),
  Error,
  "fractional cents are rejected",
);
assert.throws(
  () => foldMutualDues([{ who: "", whom: "jon", cents: 5 }]),
  Error,
  "an empty name is rejected",
);
assert.throws(
  () => foldMutualDues([["ivy", "jon", 5]]),
  Error,
  "a slip that is a list is rejected",
);
console.log("ok");
