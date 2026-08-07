import assert from "node:assert/strict";
import { commitIndex } from "./solution.ts";

assert.deepEqual(
  commitIndex([1, 1, 2, 2], [4, 3, 1, 2], 2),
  { commit: 3, safe: 1, behind: [2, 3] },
  "three of five hold entry three, so that is as far as the log commits",
);
assert.deepEqual(
  commitIndex([1, 1, 2], [3, 3], 3),
  { commit: 0, safe: 0, behind: [] },
  "an entry from an older term never commits, however widely it is held",
);
assert.deepEqual(
  commitIndex([1, 2, 2], [], 2),
  { commit: 3, safe: 3, behind: [] },
  "a leader with no followers is its own quorum",
);
assert.deepEqual(
  commitIndex([], [0, 0], 4),
  { commit: 0, safe: 0, behind: [] },
  "an empty log commits nothing and hides nothing",
);
assert.deepEqual(
  commitIndex([5], [0, 0], 5),
  { commit: 0, safe: 0, behind: [] },
  "the leader alone is short of a quorum of three",
);
assert.deepEqual(
  commitIndex([5], [1, 0], 5),
  { commit: 1, safe: 0, behind: [1] },
  "one follower joining the leader carries the entry over the line",
);
assert.deepEqual(
  commitIndex([1, 1], [2, 2], 1),
  { commit: 2, safe: 2, behind: [] },
  "a fully replicated log may be discarded in full",
);
assert.deepEqual(
  commitIndex([1, 2], [2, 1], 2),
  { commit: 2, safe: 1, behind: [1] },
  "the laggard holds the snapshot point back below the commit",
);
assert.deepEqual(
  commitIndex([1, 1, 1, 2, 2, 2], [6, 5, 4, 2, 1], 2),
  { commit: 4, safe: 1, behind: [3, 4] },
  "four of six is the quorum, and entry four is the deepest one reaching it",
);

assert.throws(() => commitIndex([2, 1], [0], 2), Error, "a falling term is rejected");
assert.throws(() => commitIndex([5], [0], 3), Error, "a term above the current one is rejected");
assert.throws(() => commitIndex([1, 1], [3], 1), Error, "a copied number past the log is rejected");
assert.throws(() => commitIndex([1, 1], [-1], 1), Error, "a negative copied number is rejected");
assert.throws(() => commitIndex([1, 1], [1.5], 1), Error, "a fractional copied number is rejected");
assert.throws(() => commitIndex([0], [0], 1), Error, "a term of zero is rejected");
assert.throws(() => commitIndex([1], [0], 0), Error, "a current term of zero is rejected");
assert.throws(() => commitIndex("11", [0], 1), Error, "a log given as text is rejected");
console.log("ok");
