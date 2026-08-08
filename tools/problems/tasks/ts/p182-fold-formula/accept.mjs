import assert from "node:assert/strict";
import { foldFormula } from "./solution.ts";

assert.equal(foldFormula("C"), "C", "a lone tag keeps no count");
assert.equal(foldFormula("H2O"), "H2O", "flat recipe, tags already ordered");
assert.equal(foldFormula("OH2"), "H2O", "tags are reordered by code point");
assert.equal(foldFormula("H1"), "H", "an explicit repeat of one prints nothing");
assert.equal(foldFormula("Mg(OH)2"), "H2MgO2", "group repeat multiplies inside");
assert.equal(
  foldFormula("K4(ON(SO3)2)2"),
  "K4N2O14S4",
  "nested groups multiply through",
);
assert.equal(foldFormula("((H)2)3"), "H6", "repeats compose across depths");
assert.equal(foldFormula("(Uue)3"), "Uue3", "a three-letter tag is legal");
assert.equal(foldFormula("CaCO3"), "CCaO3", "one and two letter tags sort apart");
assert.equal(foldFormula("NaClNaCl"), "Cl2Na2", "a repeated tag accumulates");
assert.equal(
  foldFormula("(NH4)2SO4"),
  "H8N2O4S",
  "a group followed by more items",
);
assert.equal(foldFormula("H12"), "H12", "a two digit repeat is one number");

assert.throws(() => foldFormula(""), Error, "the empty recipe is rejected");
assert.throws(() => foldFormula("(H2O"), Error, "an open parenthesis is rejected");
assert.throws(() => foldFormula("H2O)"), Error, "a lone closer is rejected");
assert.throws(() => foldFormula("()"), Error, "an empty group is rejected");
assert.throws(() => foldFormula("H0"), Error, "a zero repeat is rejected");
assert.throws(() => foldFormula("H02"), Error, "a leading zero is rejected");
assert.throws(() => foldFormula("h2o"), Error, "a lowercase start is rejected");
assert.throws(() => foldFormula("Uuea"), Error, "a four letter tag is rejected");
assert.throws(() => foldFormula(42), Error, "a non-string is rejected");
console.log("ok");
