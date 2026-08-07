import assert from "node:assert/strict";
import { strandMarkSheet } from "./solution.ts";

const one = (work, discard = 0) => [
  { name: "s", share: 1000, discard, work },
];

assert.deepEqual(
  strandMarkSheet(one([[5, 5], [5, 5]])),
  { mark: 1000, discarded: [] },
  "everything scored and nothing discarded reads 1000"
);

assert.deepEqual(
  strandMarkSheet(one([[8, 10], [5, 10], [9, 10]], 1)),
  { mark: 850, discarded: ["s#1"] },
  "the weakest of three goes"
);

assert.deepEqual(
  strandMarkSheet(one([[1, 2], [3, 10]], 1)),
  { mark: 500, discarded: ["s#1"] },
  "weakness is the ratio, not the raw score"
);

assert.deepEqual(
  strandMarkSheet(one([["absent", 10], [7, 10]])),
  { mark: 350, discarded: [] },
  "an absent piece still occupies its availability"
);

assert.deepEqual(
  strandMarkSheet(one([["absent", 5], [4, 5], [3, 5]], 1)),
  { mark: 700, discarded: ["s#0"] },
  "an absent piece is the weakest there is"
);

assert.deepEqual(
  strandMarkSheet(one([[1, 4], [2, 4]], 5)),
  { mark: 500, discarded: ["s#0"] },
  "a runaway discard count still leaves the strongest piece"
);

assert.deepEqual(
  strandMarkSheet(one([[1, 2], [2, 4], [9, 10]], 1)),
  { mark: 833, discarded: ["s#1"] },
  "equal ratios break toward the piece available for more"
);

assert.deepEqual(
  strandMarkSheet(one([[1, 2], [1, 2], [9, 10]], 1)),
  { mark: 833, discarded: ["s#0"] },
  "identical pieces break toward the earlier position"
);

assert.deepEqual(
  strandMarkSheet([
    { name: "A", share: 600, discard: 1, work: [[3, 5], [4, 5]] },
    { name: "B", share: 400, discard: 2, work: [[1, 3], [2, 3], ["absent", 3]] },
  ]),
  { mark: 746, discarded: ["A#0", "B#2", "B#0"] },
  "strands in order, weakest first inside a strand"
);

assert.throws(() => strandMarkSheet([]), Error, "an empty report is rejected");
assert.throws(
  () =>
    strandMarkSheet([
      { name: "x", share: 500, discard: 0, work: [[1, 1]] },
      { name: "x", share: 500, discard: 0, work: [[1, 1]] },
    ]),
  Error,
  "a repeated strand name is rejected"
);
assert.throws(
  () => strandMarkSheet([{ name: "x", share: 900, discard: 0, work: [[1, 1]] }]),
  Error,
  "shares that miss 1000 are rejected"
);
assert.throws(
  () => strandMarkSheet(one([[1, 1]], -1)),
  Error,
  "a negative discard count is rejected"
);
assert.throws(
  () => strandMarkSheet(one([])),
  Error,
  "a strand with no work is rejected"
);
assert.throws(
  () => strandMarkSheet(one([[0, 0]])),
  Error,
  "a piece available for nothing is rejected"
);
assert.throws(
  () => strandMarkSheet(one([[4, 3]])),
  Error,
  "a score above its availability is rejected"
);
assert.throws(
  () => strandMarkSheet(one([[-2, 3]])),
  Error,
  "a negative score is rejected"
);
assert.throws(
  () => strandMarkSheet(one([["late", 3]])),
  Error,
  "an unknown score word is rejected"
);

console.log("ok");
