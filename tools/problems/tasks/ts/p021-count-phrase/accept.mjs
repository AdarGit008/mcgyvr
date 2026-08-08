import assert from "node:assert/strict";
import { countPhrase } from "./solution.ts";

assert.equal(countPhrase(["the", "cat", "sat"], "cat"), 1, "one plain hit");
assert.equal(
  countPhrase(["the", "catalog", "sat"], "cat"),
  0,
  "a longer word is not a hit",
);
assert.equal(countPhrase(["The", "CAT", "sat"], "cat"), 1, "token case is ignored");
assert.equal(countPhrase(["cat"], "Cat"), 1, "phrase case is ignored too");
assert.equal(
  countPhrase(["big", "dog", "big", "dog"], "big dog"),
  2,
  "two separate hits",
);
assert.equal(
  countPhrase(["a", "a", "a"], "a a"),
  1,
  "overlapping hits count once",
);
assert.equal(
  countPhrase(["big", "dog", "dog"], "big dog"),
  1,
  "a trailing token does not double count",
);
assert.equal(countPhrase(["one", "two"], "three"), 0, "no hit at all");
assert.equal(countPhrase([], "x"), 0, "no tokens, no hits");
assert.throws(() => countPhrase(["a"], ""), Error, "empty phrase rejected");
assert.throws(() => countPhrase(["a"], "   "), Error, "blank phrase rejected");
console.log("ok");
