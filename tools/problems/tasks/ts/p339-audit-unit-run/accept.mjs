import assert from "node:assert/strict";
import { auditUnitRun } from "./solution.ts";

assert.deepEqual(
  auditUnitRun(5, 6, [2, 3]),
  { verdict: "exact", gap: [0, 1] },
  "a claim the pieces land on exactly",
);
assert.deepEqual(
  auditUnitRun(3, 7, [3, 11, 231]),
  { verdict: "exact", gap: [0, 1] },
  "three pieces landing on three sevenths",
);
assert.deepEqual(
  auditUnitRun(7, 10, [2, 5]),
  { verdict: "exact", gap: [0, 1] },
  "two pieces landing on seven tenths",
);
assert.deepEqual(
  auditUnitRun(1, 2, [3]),
  { verdict: "short", gap: [1, 6] },
  "one piece falling beneath the claim",
);
assert.deepEqual(
  auditUnitRun(1, 3, [2]),
  { verdict: "over", gap: [-1, 6] },
  "one piece overshooting the claim, minus sign on the top",
);
assert.deepEqual(
  auditUnitRun(0, 5, []),
  { verdict: "exact", gap: [0, 1] },
  "nothing claimed and nothing offered",
);
assert.deepEqual(
  auditUnitRun(0, 5, [2]),
  { verdict: "over", gap: [-1, 2] },
  "a piece offered against a claim of nothing",
);
assert.deepEqual(
  auditUnitRun(1, 2, []),
  { verdict: "short", gap: [1, 2] },
  "an empty run judged against a real claim",
);
assert.deepEqual(
  auditUnitRun(1, 1, [2, 3, 6]),
  { verdict: "exact", gap: [0, 1] },
  "a claim of one, met exactly",
);
assert.deepEqual(
  auditUnitRun(2, 1, [2, 3, 6]),
  { verdict: "short", gap: [1, 1] },
  "a claim above one leaves a whole gap",
);
assert.deepEqual(
  auditUnitRun(2, 4, [2]),
  { verdict: "exact", gap: [0, 1] },
  "a claim written unreduced is judged on its value",
);

assert.throws(
  () => auditUnitRun(1, 2, [99989, 99991]),
  Error,
  "a running total whose bottom passes the ceiling is rejected",
);
assert.throws(() => auditUnitRun(1, 2, [1]), Error, "a piece below two is rejected");
assert.throws(() => auditUnitRun(1, 2, [3, 3]), Error, "a repeated piece is rejected");
assert.throws(() => auditUnitRun(1, 2, [3, 2]), Error, "pieces out of order are rejected");
assert.throws(
  () => auditUnitRun(1, 2, [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]),
  Error,
  "more than ten pieces is rejected",
);
assert.throws(() => auditUnitRun(1, 2, [100001]), Error, "a piece past the ceiling is rejected");
assert.throws(() => auditUnitRun(1, 2, [2.5]), Error, "a fractional piece is rejected");
assert.throws(() => auditUnitRun(1, 2, "23"), Error, "a run that is not a list is rejected");
assert.throws(() => auditUnitRun(-1, 2, []), Error, "a negative top is rejected");
assert.throws(() => auditUnitRun(1, 0, []), Error, "a bottom of nothing is rejected");
assert.throws(() => auditUnitRun(1, 100001, []), Error, "a bottom past the ceiling is rejected");
console.log("ok");
