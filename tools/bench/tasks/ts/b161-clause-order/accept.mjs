import assert from "node:assert/strict";
import { clauseOrder } from "./solution.ts";

assert.equal(clauseOrder("3.2", "3.2"), 0, "identical marks are equal");
assert.equal(clauseOrder("1.9", "1.10"), -1, "numbers compare numerically, not as text");
assert.equal(clauseOrder("2.1", "1.9"), 1, "a later front number wins");
assert.equal(clauseOrder("3.2", "3.2.1"), -1, "a mark that extends another comes after it");
assert.equal(clauseOrder("4.1.1", "4.1"), 1, "the extended mark is the later one");
assert.equal(clauseOrder("7", "11"), -1, "single numbers compare numerically");
assert.equal(clauseOrder("10.0", "9.9"), 1, "the front number outranks the rest");
assert.throws(() => clauseOrder(3.2, "1"), Error, "a non-string mark is rejected");
assert.throws(() => clauseOrder("", "1"), Error, "an empty mark is rejected");
assert.throws(() => clauseOrder("1..2", "1"), Error, "an empty number from a stray dot is rejected");
assert.throws(() => clauseOrder("1.02", "1"), Error, "a leading zero is rejected");
assert.throws(() => clauseOrder("1.2a", "1"), Error, "a stray character is rejected");
console.log("ok");
