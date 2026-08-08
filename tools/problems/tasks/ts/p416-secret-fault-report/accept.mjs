import assert from "node:assert/strict";
import { reportSecretFaults } from "./solution.ts";

// Every phrase below is nonsense stitched together here for the check.
const head = "Ab3";
const house = {
  least: 8,
  most: 16,
  needs: ["lower", "upper", "digit"],
  forbidden: ["woof", "meow"],
};

assert.deepEqual(
  reportSecretFaults(head + "defgh", house),
  [],
  "a phrase meeting every rule breaks none",
);
assert.deepEqual(
  reportSecretFaults(head, house),
  ["short"],
  "a phrase under least is short",
);
assert.deepEqual(
  reportSecretFaults(head + "defghijklmnopq", house),
  ["long"],
  "a phrase over most is long",
);
assert.deepEqual(
  reportSecretFaults("abcdefgh", house),
  ["upper", "digit"],
  "missing classes come out in the fixed class order",
);
assert.deepEqual(
  reportSecretFaults("ABCDEFGH", house),
  ["lower", "digit"],
  "lower is named before digit however needs was written",
);
assert.deepEqual(
  reportSecretFaults(head + " defgh", house),
  ["stray"],
  "a space belongs to no class",
);
assert.deepEqual(
  reportSecretFaults(head + "woofxx", house),
  ["forbidden"],
  "a forbidden word inside the phrase is caught",
);
assert.deepEqual(
  reportSecretFaults(head + "WOOFxx", house),
  ["forbidden"],
  "the phrase is lowered before the forbidden words are sought",
);
assert.deepEqual(
  reportSecretFaults("ab", house),
  ["short", "upper", "digit"],
  "length comes before the classes",
);
assert.deepEqual(
  reportSecretFaults("ab~", house),
  ["short", "stray", "upper", "digit"],
  "stray sits between the length rules and the classes",
);
assert.deepEqual(
  reportSecretFaults("ab" + "meow" + "~", house),
  ["short", "stray", "upper", "digit", "forbidden"],
  "forbidden is always last on the list",
);

const marky = { least: 1, most: 20, needs: ["mark"], forbidden: [] };
assert.deepEqual(
  reportSecretFaults("abcdefgh", marky),
  ["mark"],
  "a policy needing a mark reports its absence",
);
assert.deepEqual(
  reportSecretFaults("abcdefg!", marky),
  [],
  "an exclamation counts as a mark",
);
assert.deepEqual(
  reportSecretFaults(head + "-", marky),
  [],
  "the hyphen is one of the ten marks",
);
assert.deepEqual(
  reportSecretFaults("", marky),
  ["short", "mark"],
  "an empty phrase is short and classless",
);

assert.throws(
  () => reportSecretFaults(42, house),
  Error,
  "a phrase that is a number is rejected",
);
assert.throws(
  () => reportSecretFaults("abcdefgh", { least: 8, most: 16, needs: ["lower"] }),
  Error,
  "a policy without forbidden is rejected",
);
assert.throws(
  () =>
    reportSecretFaults("abcdefgh", {
      least: 0,
      most: 16,
      needs: ["lower"],
      forbidden: [],
    }),
  Error,
  "a least of zero is rejected",
);
assert.throws(
  () =>
    reportSecretFaults("abcdefgh", {
      least: 9,
      most: 8,
      needs: ["lower"],
      forbidden: [],
    }),
  Error,
  "a most below least is rejected",
);
assert.throws(
  () =>
    reportSecretFaults("abcdefgh", {
      least: 1,
      most: 8,
      needs: [],
      forbidden: [],
    }),
  Error,
  "an empty needs list is rejected",
);
assert.throws(
  () =>
    reportSecretFaults("abcdefgh", {
      least: 1,
      most: 8,
      needs: ["vowel"],
      forbidden: [],
    }),
  Error,
  "a class outside the four is rejected",
);
assert.throws(
  () =>
    reportSecretFaults("abcdefgh", {
      least: 1,
      most: 8,
      needs: ["lower", "lower"],
      forbidden: [],
    }),
  Error,
  "one class named twice is rejected",
);
assert.throws(
  () =>
    reportSecretFaults("abcdefgh", {
      least: 1,
      most: 8,
      needs: ["lower"],
      forbidden: ["Woof"],
    }),
  Error,
  "a forbidden word with a capital is rejected",
);
assert.throws(
  () =>
    reportSecretFaults("abcdefgh", {
      least: 1,
      most: 8,
      needs: ["lower"],
      forbidden: [""],
    }),
  Error,
  "an empty forbidden word is rejected",
);
assert.throws(
  () => reportSecretFaults("abcdefgh", ["lower"]),
  Error,
  "a policy given as a list is rejected",
);
console.log("ok");
