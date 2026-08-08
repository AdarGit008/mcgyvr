import assert from "node:assert/strict";
import { rankStemmedTerms } from "./solution.ts";

const plain = { stops: [], endings: [] };

assert.deepEqual(
  rankStemmedTerms("Cats ran; the cat runs and a cat rested. Resting cats rest!", {
    stops: ["the", "a", "run"],
    endings: [
      ["ing", 3],
      ["ed", 3],
      ["s", 3],
    ],
  }),
  [
    ["cat", 4],
    ["rest", 3],
    ["and", 1],
    ["ran", 1],
  ],
  "trimming happens first and the stop list is weighed against the trimmed word",
);
assert.deepEqual(
  rankStemmedTerms("is as gas cars", { stops: [], endings: [["s", 3]] }),
  [
    ["as", 1],
    ["car", 1],
    ["gas", 1],
    ["is", 1],
  ],
  "a floor blocks the trim and equal counts sort alphabetically",
);
assert.deepEqual(
  rankStemmedTerms("Boxes boxes box", {
    stops: [],
    endings: [
      ["es", 4],
      ["s", 2],
    ],
  }),
  [
    ["boxe", 2],
    ["box", 1],
  ],
  "a pair that breaks its floor is passed over and a later pair fires",
);
assert.deepEqual(rankStemmedTerms("", plain), [], "an empty passage counts nothing");
assert.deepEqual(rankStemmedTerms("42 -- 7", plain), [], "a passage with no letters counts nothing");
assert.deepEqual(
  rankStemmedTerms("The the a A", { stops: ["the", "a"], endings: [] }),
  [],
  "a passage of nothing but stop words counts nothing",
);
assert.deepEqual(
  rankStemmedTerms("Dogs dogs DOG", plain),
  [
    ["dogs", 2],
    ["dog", 1],
  ],
  "with no endings the folded words are counted as they stand",
);
assert.deepEqual(
  rankStemmedTerms("e-mail e mail 42 mail3", plain),
  [
    ["mail", 3],
    ["e", 2],
  ],
  "digits and punctuation only separate words",
);
assert.deepEqual(
  rankStemmedTerms("runs run running", { stops: ["run"], endings: [["s", 3]] }),
  [
    ["running", 1],
  ],
  "an untrimmed spelling on the stop list is dropped only once it matches after trimming",
);
assert.deepEqual(
  rankStemmedTerms("walked walking walks walk", {
    stops: [],
    endings: [
      ["ing", 4],
      ["ed", 4],
      ["s", 4],
    ],
  }),
  [["walk", 4]],
  "several endings fold to one term",
);

assert.throws(() => rankStemmedTerms(5, plain), Error, "a non-string passage is rejected");
assert.throws(() => rankStemmedTerms("cat", null), Error, "a missing rules mapping is rejected");
assert.throws(() => rankStemmedTerms("cat", [[], []]), Error, "rules given as a list are rejected");
assert.throws(() => rankStemmedTerms("cat", { stops: [], endings: "s" }), Error, "endings that are not a list are rejected");
assert.throws(() => rankStemmedTerms("cat", { stops: "the", endings: [] }), Error, "stops that are not a list are rejected");
assert.throws(() => rankStemmedTerms("cat", { stops: ["The"], endings: [] }), Error, "a capitalised stop word is rejected");
assert.throws(() => rankStemmedTerms("cat", { stops: [""], endings: [] }), Error, "an empty stop word is rejected");
assert.throws(() => rankStemmedTerms("cat", { stops: [], endings: [["s"]] }), Error, "an endings entry that is not a pair is rejected");
assert.throws(() => rankStemmedTerms("cat", { stops: [], endings: [["S", 2]] }), Error, "a capitalised tail is rejected");
assert.throws(() => rankStemmedTerms("cat", { stops: [], endings: [["s", 0]] }), Error, "a floor of zero is rejected");
assert.throws(() => rankStemmedTerms("cat", { stops: [], endings: [["s", 1.5]] }), Error, "a fractional floor is rejected");
console.log("ok");
