import assert from "node:assert/strict";
import { threadScore, threadDepth, countAwarded, pruneDeleted } from "./solution.ts";

const c = (score, deleted = false, ...replies) => ({ score, deleted, replies });

assert.equal(threadScore(c(5)), 5, "lone comment scores itself");
assert.equal(threadScore(c(1, false, c(2), c(3))), 6, "direct replies count");
assert.equal(threadScore(c(1, false, c(2, false, c(4, false, c(8))))), 15, "deep nesting counts");
assert.equal(threadScore(c(7, true, c(2))), 2, "deleted root contributes nothing");
assert.equal(threadScore(c(1, false, c(10, true, c(4)))), 5, "deleted middle keeps its replies");
assert.equal(threadScore(c(-3, false, c(5))), 2, "negative scores are summed");
assert.equal(threadScore(c(9, true)), 0, "deleted lone comment is zero");
assert.throws(() => threadScore(c(2.5)), Error, "fractional score is rejected");
assert.throws(() => threadScore(c(true)), Error, "boolean score is rejected");
assert.throws(() => threadScore(c(1, false, c(2, false, c("x")))), Error, "deep bad score is rejected");
assert.equal(threadDepth(c(1)), 1, "lone comment has depth 1");
assert.equal(threadDepth(c(1, false, c(2), c(3, false, c(4)))), 3, "depth follows the longest chain");
assert.equal(countAwarded(c(5, false, c(3), c(8, true, c(10))), 5), 2, "deleted comments never awarded");
assert.equal(countAwarded(c(1), 5), 0, "no awards below the bar");
assert.equal(pruneDeleted(c(4, true)), null, "childless deleted thread prunes away");
assert.deepEqual(pruneDeleted(c(1, false, c(2, true), c(3))), c(1, false, c(3)), "childless deleted reply drops");
assert.deepEqual(pruneDeleted(c(1, true, c(2, true, c(5)))), c(1, true, c(2, true, c(5))), "chains to live leaves stay");
console.log("ok");
