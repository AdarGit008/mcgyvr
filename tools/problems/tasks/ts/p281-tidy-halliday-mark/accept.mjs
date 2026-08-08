import assert from "node:assert/strict";
import { tidyShelfMark } from "./solution.ts";

assert.equal(
  tidyShelfMark("GB-207.5-k3"),
  "GB-207.5-k3",
  "an already tidy mark is left alone",
);
assert.equal(
  tidyShelfMark("gb-207.5-K3"),
  "GB-207.5-k3",
  "the wing goes up, the peg goes down",
);
assert.equal(
  tidyShelfMark("  GB - 007.50 - k3  "),
  "GB-7.5-k3",
  "spaces go, padding goes, the fraction stays",
);
assert.equal(
  tidyShelfMark("GB-207.00-k3"),
  "GB-207-k3",
  "a fraction of nothing takes the dot with it",
);
assert.equal(tidyShelfMark("GB-012-a9"), "GB-12-a9", "left padding falls away");
assert.equal(
  tidyShelfMark("ZZ-999.99-z1"),
  "ZZ-999.99-z1",
  "the far end of the range survives",
);
assert.equal(
  tidyShelfMark("Mn-000042.100-Q7"),
  "MN-42.1-q7",
  "every tidying at once",
);
assert.throws(() => tidyShelfMark("G-1-a1"), Error, "a one-letter wing is rejected");
assert.throws(
  () => tidyShelfMark("GBC-1-a1"),
  Error,
  "a three-letter wing is rejected",
);
assert.throws(() => tidyShelfMark("GB-0-a1"), Error, "a bay of nought is rejected");
assert.throws(() => tidyShelfMark("GB-1000-a1"), Error, "a bay past 999 is rejected");
assert.throws(
  () => tidyShelfMark("GB-1.234-a1"),
  Error,
  "a fraction of three digits is rejected",
);
assert.throws(() => tidyShelfMark("GB-1.-a1"), Error, "a dangling dot is rejected");
assert.throws(() => tidyShelfMark("GB-1-a0"), Error, "a peg digit of nought is rejected");
assert.throws(() => tidyShelfMark("GB-1-ab"), Error, "a peg of two letters is rejected");
assert.throws(() => tidyShelfMark("GB-1"), Error, "a mark of two parts is rejected");
assert.throws(
  () => tidyShelfMark("GB-1-a1-x"),
  Error,
  "a mark of four parts is rejected",
);
assert.throws(() => tidyShelfMark(5), Error, "a mark that is not a string is rejected");
console.log("ok");
