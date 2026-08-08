import assert from "node:assert/strict";
import { traceUnevenPayoff } from "./solution.ts";

assert.deepEqual(
  traceUnevenPayoff(100000, 100, [30000, 500, 30000]),
  [
    [30000, 1000, 1000, 29000, 71000, 0],
    [500, 710, 500, 0, 71000, 210],
    [30000, 710, 920, 29080, 41920, 0],
    [41920, 0, 0, 41920, 0, 0],
  ],
  "a short instalment leaves a pile the next one settles before the fresh levy",
);
assert.deepEqual(
  traceUnevenPayoff(1000, 1000, [0, 0, 500]),
  [
    [0, 100, 0, 0, 1000, 100],
    [0, 100, 0, 0, 1000, 200],
    [500, 100, 300, 200, 800, 0],
    [800, 0, 0, 800, 0, 0],
  ],
  "instalments of nothing build the pile and the pile is never levied",
);
assert.deepEqual(
  traceUnevenPayoff(1000, 0, [1000]),
  [[1000, 0, 0, 1000, 0, 0]],
  "an account cleared by the last instalment gets no settlement row",
);
assert.deepEqual(
  traceUnevenPayoff(50, 100, [0]),
  [
    [0, 1, 0, 0, 50, 1],
    [51, 0, 1, 50, 0, 0],
  ],
  "an exact half cent is lifted upward and the settlement row clears the pile too",
);
assert.deepEqual(
  traceUnevenPayoff(1000, 1000, [0, 200]),
  [
    [0, 100, 0, 0, 1000, 100],
    [200, 100, 200, 0, 1000, 0],
    [1000, 0, 0, 1000, 0, 0],
  ],
  "an instalment swallowed whole by levies bites into no principal",
);
assert.deepEqual(
  traceUnevenPayoff(900, 0, [300, 300, 300]),
  [
    [300, 0, 0, 300, 600, 0],
    [300, 0, 0, 300, 300, 0],
    [300, 0, 0, 300, 0, 0],
  ],
  "a rate of nothing sends every cent to the principal",
);
assert.deepEqual(
  traceUnevenPayoff(400, 0, [0]),
  [
    [0, 0, 0, 0, 400, 0],
    [400, 0, 0, 400, 0, 0],
  ],
  "a single empty instalment leaves the settlement row to do all the work",
);
assert.equal(
  traceUnevenPayoff(1000, 1000, [0, 0, 500]).length,
  4,
  "three instalments plus a settlement make four rows",
);

assert.throws(() => traceUnevenPayoff(0, 100, [10]), Error, "an opening of zero is rejected");
assert.throws(() => traceUnevenPayoff(-5, 100, [10]), Error, "a negative opening is rejected");
assert.throws(() => traceUnevenPayoff(1.5, 100, [10]), Error, "a fractional opening is rejected");
assert.throws(() => traceUnevenPayoff(1000, -1, [10]), Error, "a negative rate is rejected");
assert.throws(() => traceUnevenPayoff(1000, 100, "10"), Error, "a non-list of instalments is rejected");
assert.throws(() => traceUnevenPayoff(1000, 100, []), Error, "an empty instalment list is rejected");
assert.throws(() => traceUnevenPayoff(1000, 100, [10, -1]), Error, "a negative instalment is rejected");
assert.throws(() => traceUnevenPayoff(1000, 100, [1.5]), Error, "a fractional instalment is rejected");
assert.throws(
  () => traceUnevenPayoff(1000, 0, [1001]),
  Error,
  "an instalment above everything owed is rejected",
);
assert.throws(
  () => traceUnevenPayoff(1000, 0, [500, 600]),
  Error,
  "an overpayment is caught partway through the run",
);
console.log("ok");
