import assert from "node:assert/strict";
import { sieveReport } from "./solution.ts";

const rules = [
  { name: "needs-badge", field: "badge", op: "present" },
  { name: "tier-cap", field: "tier", op: "lt", value: 3 },
  { name: "not-parked", field: "state", op: "ne", value: "parked" },
];
assert.deepEqual(
  sieveReport(
    [
      { badge: 1, tier: 2, state: "live" },
      { tier: 2, state: "live" },
      { badge: 1, tier: 5, state: "live" },
      { badge: 1, tier: 2, state: "parked" },
      { badge: 1, state: "live" },
      { badge: 1, tier: "high", state: "live" },
    ],
    rules,
  ),
  ["pass", "needs-badge", "tier-cap", "not-parked", "tier-cap", "tier-cap"],
  "first failing rule is named; missing and non-number fields fail",
);
assert.deepEqual(
  sieveReport([{ flag: 1 }], [{ name: "no-flag", field: "flag", op: "absent" }]),
  ["no-flag"],
  "absent fails when the field exists",
);
assert.deepEqual(
  sieveReport([{}], [{ name: "no-flag", field: "flag", op: "absent" }]),
  ["pass"],
  "absent passes when the field is missing",
);
assert.deepEqual(
  sieveReport(
    [{ kind: "ore" }, { kind: "ash" }],
    [{ name: "ore-only", field: "kind", op: "eq", value: "ore" }],
  ),
  ["pass", "ore-only"],
  "eq compares exactly",
);
assert.deepEqual(
  sieveReport([{ mass: 8 }], [{ name: "heavy", field: "mass", op: "gt", value: 8 }]),
  ["heavy"],
  "gt is strict",
);
assert.deepEqual(sieveReport([{ a: 1 }, {}], []), ["pass", "pass"], "no rules, all pass");
assert.deepEqual(sieveReport([], rules), [], "no items, no verdicts");
assert.throws(
  () => sieveReport([], [{ name: "r", field: "a", op: "ge", value: 1 }]),
  Error,
  "unknown op is rejected",
);
assert.throws(
  () =>
    sieveReport([], [
      { name: "r", field: "a", op: "eq", value: 1 },
      { name: "r", field: "b", op: "eq", value: 2 },
    ]),
  Error,
  "repeated rule name is rejected",
);
assert.throws(
  () => sieveReport([], [{ name: "", field: "a", op: "eq", value: 1 }]),
  Error,
  "empty rule name is rejected",
);
console.log("ok");
