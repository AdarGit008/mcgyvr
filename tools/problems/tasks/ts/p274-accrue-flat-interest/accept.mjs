import assert from "node:assert/strict";
import { accrueFlatInterest } from "./solution.ts";

assert.equal(
  accrueFlatInterest(100000, 500, 365, 365),
  5000,
  "a full year at five percent",
);
assert.equal(
  accrueFlatInterest(100000, 600, 30, 360),
  500,
  "one thirty-day month on a 360-day year",
);
assert.equal(
  accrueFlatInterest(5000000, 1250, 90, 360),
  156250,
  "a quarter at twelve and a half percent",
);
assert.equal(
  accrueFlatInterest(180000, 10, 1, 360),
  1,
  "exactly half a cent settles upward",
);
assert.equal(
  accrueFlatInterest(179999, 10, 1, 360),
  0,
  "a shade under half a cent settles down",
);
assert.equal(
  accrueFlatInterest(180001, 10, 1, 360),
  1,
  "a shade over half a cent settles up",
);
assert.equal(accrueFlatInterest(100000, 500, 0, 365), 0, "no days, no earnings");
assert.equal(accrueFlatInterest(0, 500, 365, 365), 0, "no principal, no earnings");
assert.equal(accrueFlatInterest(100000, 0, 365, 365), 0, "no rate, no earnings");
assert.throws(
  () => accrueFlatInterest(-1, 500, 30, 360),
  Error,
  "a negative principal is rejected",
);
assert.throws(
  () => accrueFlatInterest(100000, -5, 30, 360),
  Error,
  "a negative rate is rejected",
);
assert.throws(
  () => accrueFlatInterest(100000, 500, -30, 360),
  Error,
  "a negative day count is rejected",
);
assert.throws(
  () => accrueFlatInterest(100000, 500, 30, 366),
  Error,
  "an unknown year basis is rejected",
);
assert.throws(
  () => accrueFlatInterest(100.5, 500, 30, 360),
  Error,
  "a fractional principal is rejected",
);
assert.throws(
  () => accrueFlatInterest("100000", 500, 30, 360),
  Error,
  "a principal that is not a number is rejected",
);
console.log("ok");
