import assert from "node:assert/strict";
import { splitOnce, parsePair } from "./solution.ts";

assert.deepEqual(splitOnce("a:b"), ["a", "b"], "broken at the colon");
assert.deepEqual(splitOnce("a:b:c"), ["a", "b:c"], "only the first colon breaks");
assert.deepEqual(parsePair(" a : b "), ["a", "b"], "the spaces are trimmed");
assert.deepEqual(parsePair("a:"), ["a", ""], "an empty value");
assert.deepEqual(parsePair(":b"), ["", "b"], "an empty key");
assert.throws(() => parsePair("plain"), Error, "a line with no colon is rejected");
console.log("ok");
