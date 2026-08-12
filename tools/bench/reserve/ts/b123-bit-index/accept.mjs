import assert from "node:assert/strict";
import { buildBitIndex, rankOnes, selectOne } from "./solution.ts";

const idx = buildBitIndex([2147487753, 4098], 45);
assert.deepEqual(
  idx,
  { words: [2147487753, 4098], length: 45, prefix: [0, 4, 6] },
  "prefix counts the set bits word by word",
);
assert.deepEqual(
  buildBitIndex([], 0),
  { words: [], length: 0, prefix: [0] },
  "a zero-length bitmap has no words",
);
assert.throws(() => buildBitIndex([4294967296], 32), Error, "word too wide");
assert.throws(() => buildBitIndex([0, 0], 32), Error, "word count mismatch");
assert.throws(() => buildBitIndex([256], 8), Error, "stray bit past length");
assert.equal(rankOnes(idx, 13), 3, "rank inside the first word");
assert.equal(rankOnes(idx, 32), 4, "rank at a word boundary");
assert.equal(rankOnes(idx, 45), 6, "rank at length counts everything");
assert.throws(() => rankOnes(idx, 46), Error, "rank past length");
assert.equal(selectOne(idx, 0), 0, "zeroth set bit");
assert.equal(selectOne(idx, 1), 3, "next set bit in the same word");
assert.equal(selectOne(idx, 2), 12, "third set bit");
assert.equal(selectOne(idx, 3), 31, "set bit at the top of a word");
assert.equal(selectOne(idx, 4), 33, "select crosses into the second word");
assert.equal(selectOne(idx, 5), 44, "last set bit of the bitmap");
assert.throws(() => selectOne(idx, 6), Error, "rank beyond the total");
assert.throws(() => selectOne(buildBitIndex([], 0), 0), Error, "empty bitmap has no ones");
console.log("ok");
