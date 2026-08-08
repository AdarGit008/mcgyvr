import assert from "node:assert/strict";
import { foldDimensionTerms } from "./solution.ts";

const term = (op, count, units) => ({ op, count, units });

assert.deepEqual(
  foldDimensionTerms([term("=", 6, { glim: 1 })]),
  { count: 6, units: { glim: 1 } },
  "one term is the running quantity already",
);
assert.deepEqual(
  foldDimensionTerms([term("=", 6, { glim: 1 }), term("*", 5, { spen: 1 })]),
  { count: 30, units: { glim: 1, spen: 1 } },
  "multiplying gathers both unit names",
);
assert.deepEqual(
  foldDimensionTerms([term("=", 12, { glim: 2 }), term("/", 4, { glim: 1 })]),
  { count: 3, units: { glim: 1 } },
  "dividing takes an exponent away",
);
assert.deepEqual(
  foldDimensionTerms([term("=", 10, { glim: 1 }), term("/", 5, { glim: 1 })]),
  { count: 2, units: {} },
  "an exponent driven to zero leaves the answer entirely",
);
assert.deepEqual(
  foldDimensionTerms([term("=", 2, { glim: 1 }), term("*", 3, { glim: -1 })]),
  { count: 6, units: {} },
  "a negative exponent cancels a positive one",
);
assert.deepEqual(
  foldDimensionTerms([
    term("=", 3, { glim: 1, spen: -1 }),
    term("+", 4, { spen: -1, glim: 1 }),
  ]),
  { count: 7, units: { glim: 1, spen: -1 } },
  "like quantities add however their names are arranged",
);
assert.deepEqual(
  foldDimensionTerms([term("=", 3, { glim: 1 }), term("-", 5, { glim: 1 })]),
  { count: -2, units: { glim: 1 } },
  "taking away may leave the count below zero",
);
assert.deepEqual(
  foldDimensionTerms([term("=", 5, {}), term("*", 4, { thod: 2 })]),
  { count: 20, units: { thod: 2 } },
  "a quantity with no dimension may still pick one up",
);
assert.deepEqual(
  foldDimensionTerms([term("=", 0, { glim: 1 }), term("*", -3, {})]),
  { count: 0, units: { glim: 1 } },
  "a count of nothing stays plain zero",
);
assert.deepEqual(
  foldDimensionTerms([
    term("=", 100, { glim: 1 }),
    term("/", 4, { spen: 1 }),
    term("*", 3, {}),
  ]),
  { count: 75, units: { glim: 1, spen: -1 } },
  "a chain of terms folds left to right",
);
assert.deepEqual(
  foldDimensionTerms([term("=", -6, { glim: 1 }), term("/", -2, {})]),
  { count: 3, units: { glim: 1 } },
  "two negatives divide out whole",
);

assert.throws(
  () => foldDimensionTerms([]),
  Error,
  "an empty term list is rejected",
);
assert.throws(
  () => foldDimensionTerms([term("*", 2, {})]),
  Error,
  "a first op that is not = is rejected",
);
assert.throws(
  () => foldDimensionTerms([term("=", 2, {}), term("^", 2, {})]),
  Error,
  "an op outside the four is rejected",
);
assert.throws(
  () => foldDimensionTerms([term("=", 7, {}), term("/", 2, {})]),
  Error,
  "a division that does not come out whole is rejected",
);
assert.throws(
  () => foldDimensionTerms([term("=", 7, {}), term("/", 0, {})]),
  Error,
  "dividing by a count of zero is rejected",
);
assert.throws(
  () =>
    foldDimensionTerms([term("=", 3, { glim: 1 }), term("+", 4, { spen: 1 })]),
  Error,
  "adding a different unit name is rejected",
);
assert.throws(
  () =>
    foldDimensionTerms([term("=", 3, { glim: 1 }), term("-", 4, { glim: 2 })]),
  Error,
  "adding the same name at another exponent is rejected",
);
assert.throws(
  () => foldDimensionTerms([term("=", 1.5, {})]),
  Error,
  "a fractional count is rejected",
);
assert.throws(
  () => foldDimensionTerms([term("=", 2, { glim: 0 })]),
  Error,
  "an exponent of zero is rejected",
);
assert.throws(
  () => foldDimensionTerms([term("=", 2, { glim: 1.5 })]),
  Error,
  "a fractional exponent is rejected",
);
assert.throws(
  () => foldDimensionTerms([term("=", 2, { Glim: 1 })]),
  Error,
  "a unit name outside the small letters is rejected",
);
assert.throws(
  () => foldDimensionTerms([term("=", 2, "glim")]),
  Error,
  "units that are not a mapping are rejected",
);
assert.throws(
  () => foldDimensionTerms(["="]),
  Error,
  "a term that is not a mapping is rejected",
);
assert.throws(
  () => foldDimensionTerms("terms"),
  Error,
  "terms that are not a list are rejected",
);
console.log("ok");
