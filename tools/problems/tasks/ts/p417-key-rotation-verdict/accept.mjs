import assert from "node:assert/strict";
import { judgeKeyRotation } from "./solution.ts";

// The digests below are four-character stand-ins made up here, not real ones.
const past = [
  { digest: "aa11", step: 0 },
  { digest: "bb22", step: 5 },
  { digest: "cc33", step: 9 },
];
const house = { keep: 2, gap: 2, span: 30, runs: 3, window: 12 };

assert.deepEqual(
  judgeKeyRotation(past, { digest: "dd44", step: 12 }, house),
  { verdict: "accept", broken: [] },
  "a fresh digest at a sensible step is accepted",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "aa11", step: 12 }, house),
  { verdict: "accept", broken: [] },
  "a digest older than the keep window may come round again",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "cc33", step: 12 }, house),
  { verdict: "refuse", broken: ["reused"] },
  "the newest digest is still inside the keep window",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "bb22", step: 12 }, house),
  { verdict: "refuse", broken: ["reused"] },
  "the keep window reaches back exactly two digests",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "dd44", step: 10 }, house),
  { verdict: "refuse", broken: ["toosoon", "churn"] },
  "a hurried offer breaks the gap rule and the run rule together",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "dd44", step: 50 }, house),
  { verdict: "refuse", broken: ["stale"] },
  "a difference above span is stale and no longer counts as churn",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "bb22", step: 50 }, house),
  { verdict: "refuse", broken: ["reused", "stale"] },
  "reused is always named before stale",
);
const roomy = { ...house, runs: 9 };
assert.deepEqual(
  judgeKeyRotation(past, { digest: "dd44", step: 11 }, roomy),
  { verdict: "accept", broken: [] },
  "a difference exactly equal to gap passes",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "dd44", step: 10 }, roomy),
  { verdict: "refuse", broken: ["toosoon"] },
  "one step short of gap is too soon",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "dd44", step: 39 }, roomy),
  { verdict: "accept", broken: [] },
  "a difference exactly equal to span passes",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "dd44", step: 40 }, roomy),
  { verdict: "refuse", broken: ["stale"] },
  "one step past span is stale",
);
assert.deepEqual(
  judgeKeyRotation([], { digest: "aa11", step: 0 }, house),
  { verdict: "accept", broken: [] },
  "an empty ledger has no gap, no staleness and no churn",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "cc33", step: 12 }, { ...house, keep: 0 }),
  { verdict: "accept", broken: [] },
  "a keep of zero lets any digest through",
);
assert.deepEqual(
  judgeKeyRotation(past, { digest: "aa11", step: 12 }, { ...house, keep: 9 }),
  { verdict: "refuse", broken: ["reused"] },
  "a keep past the ledger length reaches the whole ledger",
);
assert.deepEqual(
  judgeKeyRotation(
    [{ digest: "aa11", step: 0 }],
    { digest: "bb22", step: 1 },
    { keep: 1, gap: 0, span: 100, runs: 1, window: 5 },
  ),
  { verdict: "refuse", broken: ["churn"] },
  "a runs of one refuses any second change inside the window",
);
assert.deepEqual(
  judgeKeyRotation(
    [{ digest: "aa11", step: 0 }],
    { digest: "bb22", step: 5 },
    { keep: 1, gap: 0, span: 100, runs: 1, window: 5 },
  ),
  { verdict: "accept", broken: [] },
  "an entry exactly a window back has already left the window",
);

assert.throws(
  () => judgeKeyRotation("aa11", { digest: "bb22", step: 1 }, house),
  Error,
  "a ledger given as a string is rejected",
);
assert.throws(
  () => judgeKeyRotation([{ digest: "aa11" }], { digest: "bb22", step: 1 }, house),
  Error,
  "an entry without a step is rejected",
);
assert.throws(
  () => judgeKeyRotation([{ digest: "AA11", step: 0 }], { digest: "bb22", step: 1 }, house),
  Error,
  "a digest with capitals is rejected",
);
assert.throws(
  () => judgeKeyRotation([{ digest: "", step: 0 }], { digest: "bb22", step: 1 }, house),
  Error,
  "an empty digest is rejected",
);
assert.throws(
  () =>
    judgeKeyRotation(
      [
        { digest: "aa11", step: 4 },
        { digest: "bb22", step: 4 },
      ],
      { digest: "cc33", step: 9 },
      house,
    ),
  Error,
  "a ledger whose steps do not rise is rejected",
);
assert.throws(
  () => judgeKeyRotation(past, { digest: "dd44", step: 9 }, house),
  Error,
  "an offer level with the newest ledger step is rejected",
);
assert.throws(
  () => judgeKeyRotation(past, { digest: "dd44", step: 12 }, { keep: 2, gap: 2, span: 30, runs: 3 }),
  Error,
  "rules without window is rejected",
);
assert.throws(
  () => judgeKeyRotation(past, { digest: "dd44", step: 12 }, { ...house, keep: -1 }),
  Error,
  "a negative keep is rejected",
);
assert.throws(
  () => judgeKeyRotation(past, { digest: "dd44", step: 12 }, { ...house, runs: 0 }),
  Error,
  "a runs of zero is rejected",
);
assert.throws(
  () => judgeKeyRotation(past, { digest: "dd44", step: 12 }, { ...house, gap: 40 }),
  Error,
  "a gap larger than span is rejected",
);
console.log("ok");
