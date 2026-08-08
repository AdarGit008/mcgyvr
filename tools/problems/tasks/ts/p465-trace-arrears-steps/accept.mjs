import assert from "node:assert/strict";
import { traceArrearsSteps } from "./solution.ts";

assert.deepEqual(
  traceArrearsSteps(1000, 20, [
    { kind: "check", day: 20 },
    { kind: "check", day: 21 },
    { kind: "check", day: 29 },
    { kind: "check", day: 30 },
    { kind: "pay", day: 31, cents: 400 },
    { kind: "check", day: 40 },
    { kind: "check", day: 56 },
    { kind: "check", day: 75 },
    { kind: "check", day: 76 },
    { kind: "pay", day: 80, cents: 600 },
    { kind: "check", day: 200 },
  ]),
  [
    "current",
    "reminder",
    "reminder",
    "warning",
    "reminder",
    "demand",
    "demand",
    "referred",
    "settled",
  ],
  "every band edge, a re-anchoring payment and the closing one",
);

assert.deepEqual(
  traceArrearsSteps(100, 50, [{ kind: "check", day: 10 }]),
  ["current"],
  "a check before the due day reads current",
);

assert.deepEqual(
  traceArrearsSteps(500, 0, [
    { kind: "pay", day: 1, cents: 900 },
    { kind: "check", day: 2 },
  ]),
  ["settled"],
  "paying more than is owed closes the matter",
);

assert.deepEqual(
  traceArrearsSteps(500, 0, [
    { kind: "pay", day: 3, cents: 499 },
    { kind: "check", day: 12 },
    { kind: "check", day: 13 },
  ]),
  ["reminder", "warning"],
  "one cent left over keeps the account open and re-anchored",
);

assert.deepEqual(
  traceArrearsSteps(90, 4, []),
  [],
  "no checks put out no labels",
);

assert.deepEqual(
  traceArrearsSteps(90, 4, [
    { kind: "pay", day: 4, cents: 90 },
    { kind: "pay", day: 9, cents: 90 },
    { kind: "check", day: 400 },
  ]),
  ["settled"],
  "a payment against a closed account leaves it closed",
);

assert.throws(
  () => traceArrearsSteps(0, 4, []),
  Error,
  "an opening sum below one is rejected",
);
assert.throws(
  () => traceArrearsSteps(90, -4, []),
  Error,
  "a due day below nought is rejected",
);
assert.throws(
  () => traceArrearsSteps(90, 4, "nope"),
  Error,
  "a non-list of events is rejected",
);
assert.throws(
  () => traceArrearsSteps(90, 4, [{ kind: "nudge", day: 5 }]),
  Error,
  "an unknown kind is rejected",
);
assert.throws(
  () => traceArrearsSteps(90, 4, [{ kind: "check", day: 5, cents: 1 }]),
  Error,
  "a check carrying cents is rejected",
);
assert.throws(
  () => traceArrearsSteps(90, 4, [{ kind: "pay", day: 5 }]),
  Error,
  "a payment without cents is rejected",
);
assert.throws(
  () => traceArrearsSteps(90, 4, [{ kind: "pay", day: 5, cents: 0 }]),
  Error,
  "a payment of nothing is rejected",
);
assert.throws(
  () =>
    traceArrearsSteps(90, 4, [
      { kind: "check", day: 8 },
      { kind: "check", day: 7 },
    ]),
  Error,
  "a day stepping backwards is rejected",
);
assert.throws(
  () => traceArrearsSteps(90, 4, [{ kind: "check", day: 2.5 }]),
  Error,
  "a day that is not whole is rejected",
);
console.log("ok");
