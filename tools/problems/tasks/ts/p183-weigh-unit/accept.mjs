import assert from "node:assert/strict";
import { weighUnit } from "./solution.ts";

const table = { H: 1, C: 12, N: 14, O: 16, S: 32, Mg: 24, Uuo: 294 };

assert.equal(weighUnit("H", table), 1, "one part, no count");
assert.equal(weighUnit("H2O", table), 18, "counts on plain names");
assert.equal(weighUnit("Mg(OH)2", table), 58, "a count scales only its wrapping");
assert.equal(weighUnit("[NH4]2SO4", table), 132, "square brackets behave the same");
assert.equal(weighUnit("(C(H2)3)2", table), 36, "wrappings nest");
assert.equal(weighUnit("Uuo", table), 294, "a three letter name");
assert.equal(weighUnit("[H(O)]", table), 17, "the two shapes mix when matched");
assert.equal(weighUnit("H12", table), 12, "a two digit count is one number");

assert.throws(() => weighUnit("Xz", table), Error, "an absent name is rejected");
assert.throws(() => weighUnit("H(O]", table), Error, "a mismatched shape is rejected");
assert.throws(() => weighUnit("(H2O", table), Error, "an unanswered opener is rejected");
assert.throws(() => weighUnit("H2O)", table), Error, "a stray closer is rejected");
assert.throws(() => weighUnit("()", table), Error, "an empty wrapping is rejected");
assert.throws(() => weighUnit("H0", table), Error, "a zero count is rejected");
assert.throws(() => weighUnit("H02", table), Error, "a padded count is rejected");
assert.throws(() => weighUnit("", table), Error, "the empty spec is rejected");
assert.throws(() => weighUnit(7, table), Error, "a non-string spec is rejected");
console.log("ok");
