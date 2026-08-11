import assert from "node:assert/strict";
import { clipWords } from "./solution.ts";

assert.equal(clipWords(["alpha", "be"], 3), "alp. be", "only the long word is cut");
assert.equal(clipWords(["one", "two"], 3), "one two", "words at the width are left whole");
assert.equal(clipWords(["longer"], 2), "lo.", "a lone word is cut");
assert.equal(clipWords(["a", "b", "c"], 5), "a b c", "short words join with single spaces");
assert.equal(clipWords(["abcd", "efgh"], 1), "a. e.", "every word is cut");
assert.equal(clipWords([], 4), "", "a run holding no words");
console.log("ok");
