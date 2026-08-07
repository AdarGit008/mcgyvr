import assert from "node:assert/strict";
import { tallyHallRows } from "./solution.ts";

assert.deepEqual(
  tallyHallRows(["oxo", "=oo"]),
  ["tier0 held=1 open=2", "tier1 held=0 open=2", "hall held=1 open=4 widest=tier0"],
  "a tie in open chairs falls to the lower tier",
);
assert.deepEqual(
  tallyHallRows(["ooo"]),
  ["tier0 held=0 open=3", "hall held=0 open=3 widest=tier0"],
  "a single tier still gets a closing line",
);
assert.deepEqual(
  tallyHallRows(["xxx", "=o=", "xox"]),
  [
    "tier0 held=3 open=0",
    "tier1 held=0 open=1",
    "tier2 held=2 open=1",
    "hall held=5 open=2 widest=tier1",
  ],
  "steps are counted as neither held nor open",
);
assert.deepEqual(
  tallyHallRows(["xxxx"]),
  ["tier0 held=4 open=0", "hall held=4 open=0 widest=tier0"],
  "a full hall still names a widest tier",
);
assert.deepEqual(
  tallyHallRows(["=x=", "=o="]),
  ["tier0 held=1 open=0", "tier1 held=0 open=1", "hall held=1 open=1 widest=tier1"],
  "the widest tier need not be the first",
);
assert.equal(tallyHallRows(["ox", "xo", "oo"]).length, 4, "one line per tier plus the closing line");
assert.equal(tallyHallRows(["ox", "xo", "oo"]).at(-1), "hall held=2 open=4 widest=tier2", "the closing line sums the hall");
assert.throws(() => tallyHallRows("xox"), Error, "a hall that is not a list is rejected");
assert.throws(() => tallyHallRows([]), Error, "an empty hall is rejected");
assert.throws(() => tallyHallRows([7]), Error, "a tier that is not a string is rejected");
assert.throws(() => tallyHallRows([""]), Error, "an empty tier is rejected");
assert.throws(() => tallyHallRows(["xo", "x"]), Error, "tiers of differing width are rejected");
assert.throws(() => tallyHallRows(["xoz"]), Error, "a stray character is rejected");
assert.throws(() => tallyHallRows(["===", "xox"]), Error, "a tier with no chair is rejected");
console.log("ok");
