import assert from "node:assert/strict";
import { tightenNotePhrases } from "./solution.ts";

const book = {
  "as soon": "asn",
  "as soon as possible": "asap",
  class: "cls",
  "north road": "nrd",
  nrd: "nr",
};

assert.equal(
  tightenNotePhrases("as soon as possible", book),
  "asap",
  "the longest phrase wins over one the book happens to list first",
);
assert.equal(
  tightenNotePhrases("as soon after", book),
  "asn after",
  "a shorter phrase still matches where the longer one does not",
);
assert.equal(
  tightenNotePhrases("classroom", book),
  "classroom",
  "a phrase buried at the front of a longer word is not a match",
);
assert.equal(
  tightenNotePhrases("classy", book),
  "classy",
  "a letter straight after the run blocks the match",
);
assert.equal(
  tightenNotePhrases("the class met", book),
  "the cls met",
  "a phrase standing as its own word is written short",
);
assert.equal(
  tightenNotePhrases("As soon as possible, please.", book),
  "Asap, please.",
  "a run opening with a capital raises the contraction",
);
assert.equal(
  tightenNotePhrases("North Road runs east", book),
  "Nrd runs east",
  "a two-word phrase matches blind to case",
);
assert.equal(
  tightenNotePhrases("nrd", book),
  "nr",
  "a one-word phrase is written short like any other",
);
assert.equal(
  tightenNotePhrases("as  soon", book),
  "as  soon",
  "a doubled space parts the words too widely to match",
);
assert.equal(tightenNotePhrases("", book), "", "empty text stays empty");
assert.equal(
  tightenNotePhrases("nothing in the book here", book),
  "nothing in the book here",
  "text the book never mentions comes back untouched",
);
assert.equal(
  tightenNotePhrases("Class of 99", book),
  "Cls of 99",
  "digits after a space do not join the word before them",
);

assert.throws(
  () => tightenNotePhrases(7, book),
  Error,
  "a text that is not a string is rejected",
);
assert.throws(
  () => tightenNotePhrases("class", ["class"]),
  Error,
  "a book that is not a mapping is rejected",
);
assert.throws(
  () => tightenNotePhrases("class", { "As Soon": "asn" }),
  Error,
  "a key holding capitals is rejected",
);
assert.throws(
  () => tightenNotePhrases("class", { "as  soon": "asn" }),
  Error,
  "a key with a doubled space is rejected",
);
assert.throws(
  () => tightenNotePhrases("class", { "as-soon": "asn" }),
  Error,
  "a key holding a hyphen is rejected",
);
assert.throws(
  () => tightenNotePhrases("class", { "as soon": "" }),
  Error,
  "an empty contraction is rejected",
);
assert.throws(
  () => tightenNotePhrases("class", { "as soon": "ASN" }),
  Error,
  "a contraction in capitals is rejected",
);
assert.throws(
  () => tightenNotePhrases("class", { "as soon": 5 }),
  Error,
  "a contraction that is not a string is rejected",
);
console.log("ok");
