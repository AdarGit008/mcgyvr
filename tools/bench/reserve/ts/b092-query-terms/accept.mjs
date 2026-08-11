import assert from "node:assert/strict";
import { tokenizeQuery } from "./solution.ts";

assert.deepEqual(tokenizeQuery("oak"), [["word", "oak"]], "a lone plain word");
assert.deepEqual(tokenizeQuery("+oak"), [["must", "oak"]], "a required word drops its sign");
assert.deepEqual(tokenizeQuery("-pine"), [["not", "pine"]], "an excluded word drops its sign");
assert.deepEqual(
  tokenizeQuery('"garden chair"'),
  [["phrase", "garden chair"]],
  "a phrase keeps its inner spaces",
);
assert.deepEqual(
  tokenizeQuery('oak +cedar -pine "low table" stool'),
  [["word", "oak"], ["must", "cedar"], ["not", "pine"], ["phrase", "low table"], ["word", "stool"]],
  "kinds mix in input order",
);
assert.deepEqual(
  tokenizeQuery("  oak   bench "),
  [["word", "oak"], ["word", "bench"]],
  "extra spaces separate nothing",
);
assert.deepEqual(
  tokenizeQuery('"a b" "c d"'),
  [["phrase", "a b"], ["phrase", "c d"]],
  "phrases back to back stay apart",
);
assert.throws(() => tokenizeQuery(42), Error, "a non-string query is rejected");
assert.throws(() => tokenizeQuery(""), Error, "an empty query is rejected");
assert.throws(() => tokenizeQuery("   "), Error, "an all-space query is rejected");
assert.throws(() => tokenizeQuery('"broken'), Error, "an unclosed phrase is rejected");
assert.throws(() => tokenizeQuery('""'), Error, "an empty phrase is rejected");
assert.throws(() => tokenizeQuery("+"), Error, "a lone + is rejected");
assert.throws(() => tokenizeQuery("oak -"), Error, "a dangling - is rejected");
console.log("ok");
