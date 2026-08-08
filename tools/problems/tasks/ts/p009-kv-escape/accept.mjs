import assert from "node:assert/strict";
import { encodePairs } from "./solution.ts";

assert.equal(encodePairs([["a", "1"], ["b", "2"]]), "a=1&b=2", "plain pairs");
assert.equal(encodePairs([]), "", "empty list gives empty string");
assert.equal(encodePairs([["p", "100%"]]), "p=100%25", "percent escapes");
assert.equal(encodePairs([["q", "a&b"]]), "q=a%26b", "ampersand escapes");
assert.equal(encodePairs([["e", "x=y"]]), "e=x%3Dy", "equals escapes");
assert.equal(encodePairs([["m", "&&"]]), "m=%26%26", "every occurrence escapes");
assert.equal(
  encodePairs([["k%", "=&"]]),
  "k%25=%3D%26",
  "escapes never re-escape their own percent",
);
assert.equal(encodePairs([["b", "2"], ["a", "1"]]), "b=2&a=1", "order preserved");
assert.throws(() => encodePairs([["", "x"]]), Error, "empty key is rejected");
assert.throws(() => encodePairs([["a", 5]]), Error, "non-string value is rejected");
assert.throws(() => encodePairs([[5, "a"]]), Error, "non-string key is rejected");
console.log("ok");
