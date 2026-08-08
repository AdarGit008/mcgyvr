import assert from "node:assert/strict";
import { balanceReaction } from "./solution.ts";

assert.equal(
  balanceReaction("H2 + O2 -> H2O"),
  "2 H2 + O2 -> 2 H2O",
  "water from its parts",
);
assert.equal(
  balanceReaction("N2 + H2 -> NH3"),
  "N2 + 3 H2 -> 2 NH3",
  "a number of one is dropped",
);
assert.equal(
  balanceReaction("Fe + O2 -> Fe2O3"),
  "4 Fe + 3 O2 -> 2 Fe2O3",
  "two-letter symbols and larger numbers",
);
assert.equal(
  balanceReaction("CH4 + O2 -> CO2 + H2O"),
  "CH4 + 2 O2 -> CO2 + 2 H2O",
  "four species, two of them on the right",
);
assert.equal(balanceReaction("C + O2 -> CO"), "2 C + O2 -> 2 CO", "a bare symbol");
assert.equal(
  balanceReaction("H2O -> H2O"),
  "H2O -> H2O",
  "the same species on both sides needs nothing",
);
assert.equal(
  balanceReaction("H2O -> H2O2"),
  "",
  "no positive numbers can settle this",
);
assert.equal(
  balanceReaction("C + H2 -> CH4 + O2"),
  "",
  "a symbol reaching only one side",
);
assert.equal(
  balanceReaction("C8H18 + O2 -> CO2 + H2O"),
  "",
  "the smallest answer runs past twelve",
);
assert.throws(() => balanceReaction(7), Error, "not a string");
assert.throws(() => balanceReaction("H2 + O2"), Error, "no arrow");
assert.throws(() => balanceReaction("H2 -> O2 -> H3"), Error, "two arrows");
assert.throws(() => balanceReaction(" -> H2O"), Error, "an empty side");
assert.throws(() => balanceReaction("h2 -> h2"), Error, "a small first letter");
assert.throws(() => balanceReaction("H1 -> H1"), Error, "a count of one");
assert.throws(() => balanceReaction("H02 -> H02"), Error, "a leading zero");
assert.throws(
  () => balanceReaction("H2 + H2 -> H2O2"),
  Error,
  "the same species listed twice",
);
assert.throws(
  () => balanceReaction("H + C + N -> O + S + P"),
  Error,
  "more than five species",
);
console.log("ok");
