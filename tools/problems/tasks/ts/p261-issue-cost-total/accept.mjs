import assert from "node:assert/strict";
import { issueCostTotal } from "./solution.ts";

const arrive = (units, cents) => ({ kind: "in", units, cents });
const leave = (units) => ({ kind: "out", units });

assert.equal(issueCostTotal([]), 0, "an empty log charges nothing");
assert.equal(issueCostTotal([arrive(2, 700)]), 0, "arrivals alone charge nothing");
assert.equal(issueCostTotal([arrive(4, 25), leave(4)]), 100, "one consignment out in one go");
assert.equal(
  issueCostTotal([arrive(3, 10), leave(1), leave(1)]),
  20,
  "two small issues off the same consignment",
);
assert.equal(
  issueCostTotal([arrive(5, 10), arrive(5, 20), leave(7)]),
  90,
  "the older consignment is priced first",
);
assert.equal(
  issueCostTotal([arrive(5, 10), arrive(5, 20), leave(7), leave(3)]),
  150,
  "what the first issue left behind prices the second",
);
assert.equal(
  issueCostTotal([arrive(1, 1), arrive(1, 2), arrive(1, 4), leave(3)]),
  7,
  "an issue spanning three consignments takes each at its own price",
);
assert.equal(
  issueCostTotal([arrive(2, 50), leave(2), arrive(3, 10), leave(1)]),
  110,
  "an emptied bin refills cleanly",
);

assert.throws(() => issueCostTotal([leave(1)]), Error, "issuing from an empty bin is rejected");
assert.throws(() => issueCostTotal([arrive(2, 5), leave(3)]), Error, "issuing more than the bin holds is rejected");
assert.throws(() => issueCostTotal([{ kind: "scrap", units: 1 }]), Error, "an unknown kind is rejected");
assert.throws(() => issueCostTotal([arrive(0, 5)]), Error, "an arrival of no parts is rejected");
assert.throws(() => issueCostTotal([arrive(1.5, 5)]), Error, "a fractional unit count is rejected");
assert.throws(() => issueCostTotal([{ kind: "in", units: 2 }]), Error, "an unpriced arrival is rejected");
assert.throws(() => issueCostTotal([arrive(1, -5)]), Error, "a negative price is rejected");
assert.throws(
  () => issueCostTotal([arrive(2, 5), { kind: "out", units: 1, cents: 9 }]),
  Error,
  "a priced issue is rejected",
);
assert.throws(() => issueCostTotal("in"), Error, "a string argument is rejected");
console.log("ok");
