import assert from "node:assert/strict";
import { phraseQuantityLedger } from "./solution.ts";

const L = { 0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five" };
const SHORT = { 0: "none", 1: "a", 2: "both" };

assert.equal(phraseQuantityLedger([[2, "kite", "kites"]], L), "two kites", "a single stock");
assert.equal(phraseQuantityLedger([[1, "kite", "kites"]], L), "one kite", "a stock of one takes the one wording");
assert.equal(phraseQuantityLedger([[0, "kite", "kites"]], L), "nothing at all", "a stock of nought is thrown away");
assert.equal(phraseQuantityLedger([], L), "nothing at all", "an empty ledger");
assert.equal(
  phraseQuantityLedger([[2, "kite", "kites"], [3, "drum", "drums"]], L),
  "two kites and three drums",
  "two stocks are tied by and",
);
assert.equal(
  phraseQuantityLedger([[1, "kite", "kites"], [1, "drum", "drums"], [4, "flag", "flags"]], L),
  "one kite, one drum, and four flags",
  "three stocks take commas and a closing and",
);
assert.equal(
  phraseQuantityLedger([[2, "kite", "kites"], [3, "drum", "drums"], [3, "kite", "kites"]], L),
  "five kites and three drums",
  "a repeated wording folds into its first position",
);
assert.equal(
  phraseQuantityLedger([[0, "kite", "kites"], [1, "kite", "kites"]], L),
  "one kite",
  "a fold landing on one takes the one wording",
);
assert.equal(
  phraseQuantityLedger([[0, "kite", "kites"], [0, "kite", "kites"], [2, "drum", "drums"]], L),
  "two drums",
  "a fold landing on nought is thrown away",
);
assert.equal(phraseQuantityLedger([[7, "kite", "kites"]], L), "7 kites", "a tally past the lexicon is written in figures");
assert.equal(
  phraseQuantityLedger([[4, "kite", "kites"], [4, "kite", "kites"]], L),
  "8 kites",
  "a fold may carry the tally past the lexicon",
);
assert.equal(
  phraseQuantityLedger([[1, "kite", "kites"], [2, "drum", "drums"]], SHORT),
  "a kite and both drums",
  "the lexicon alone decides the tally words",
);
assert.equal(
  phraseQuantityLedger([[1, "ox", "oxen"], [2, "hen", "hens"], [3, "cat", "cats"], [1, "dog", "dogs"]], L),
  "one ox, two hens, three cats, and one dog",
  "four stocks keep their first-seen order",
);

assert.throws(() => phraseQuantityLedger([[2, "kite"]], L), Error, "a line that is not a triple is refused");
assert.throws(() => phraseQuantityLedger([[1000, "kite", "kites"]], L), Error, "a tally over 999 is refused");
assert.throws(() => phraseQuantityLedger([[-1, "kite", "kites"]], L), Error, "a tally under nought is refused");
assert.throws(() => phraseQuantityLedger([[2.5, "kite", "kites"]], L), Error, "a fractional tally is refused");
assert.throws(() => phraseQuantityLedger([[2, "", "kites"]], L), Error, "an empty wording is refused");
assert.throws(() => phraseQuantityLedger([[2, "kite9", "kites"]], L), Error, "a wording with a figure in it is refused");
assert.throws(() => phraseQuantityLedger([[2, "kite", "Kites"]], L), Error, "a wording with a capital is refused");
assert.throws(
  () => phraseQuantityLedger([[1, "kite", "kites"], [2, "kite", "kiten"]], L),
  Error,
  "two many wordings for one stock are refused",
);
assert.throws(() => phraseQuantityLedger([[1, "kite", "kites"]], { 1: "one" }), Error, "a lexicon not starting at 0 is refused");
assert.throws(() => phraseQuantityLedger([[1, "kite", "kites"]], { 0: "no", 2: "two" }), Error, "a gap in the lexicon is refused");
assert.throws(() => phraseQuantityLedger([[1, "kite", "kites"]], { 0: "no" }), Error, "a lexicon stopping at 0 is refused");
assert.throws(() => phraseQuantityLedger([[1, "kite", "kites"]], { 0: "No", 1: "one" }), Error, "a lexicon word with a capital is refused");
assert.throws(() => phraseQuantityLedger([[1, "kite", "kites"]], ["no", "one"]), Error, "a lexicon that is not a mapping is refused");
console.log("ok");
