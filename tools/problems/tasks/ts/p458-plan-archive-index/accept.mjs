import assert from "node:assert/strict";
import { planArchiveIndex } from "./solution.ts";

assert.deepEqual(
  planArchiveIndex([["a", 0, 4], ["b", 4, 6]], 10),
  { fault: "", blame: [], order: ["a", "b"], gaps: [], slack: 0, used: 10 },
  "two members butted together fill the archive exactly",
);
assert.deepEqual(
  planArchiveIndex([["b", 6, 2], ["a", 1, 3]], 12),
  { fault: "", blame: [], order: ["a", "b"], gaps: [[0, 1], [4, 2]], slack: 4, used: 5 },
  "the index is read in offset order and the holes are named",
);
assert.deepEqual(
  planArchiveIndex([], 8),
  { fault: "", blame: [], order: [], gaps: [], slack: 8, used: 0 },
  "an index with nothing in it is all trailing room",
);
assert.deepEqual(
  planArchiveIndex([], 0),
  { fault: "", blame: [], order: [], gaps: [], slack: 0, used: 0 },
  "an empty index over an empty archive",
);
assert.deepEqual(
  planArchiveIndex([["mark", 5, 0], ["a", 0, 10]], 10),
  { fault: "", blame: [], order: ["a", "mark"], gaps: [], slack: 0, used: 10 },
  "a member of no length inside another is not a clash",
);
assert.deepEqual(
  planArchiveIndex([["mark", 10, 0], ["a", 0, 10]], 10),
  { fault: "", blame: [], order: ["a", "mark"], gaps: [], slack: 0, used: 10 },
  "a member of no length may sit on the very end",
);
assert.deepEqual(
  planArchiveIndex([["a", 0, 4], ["b", 8, 5]], 10),
  { fault: "truncated", blame: ["b"], order: ["a", "b"], gaps: [], slack: 0, used: 0 },
  "a member reaching past the end is called truncated",
);
assert.deepEqual(
  planArchiveIndex([["z", 11, 0]], 10),
  { fault: "truncated", blame: ["z"], order: ["z"], gaps: [], slack: 0, used: 0 },
  "even a member of no length must start inside the archive",
);
assert.deepEqual(
  planArchiveIndex([["a", 0, 5], ["b", 3, 4]], 20),
  { fault: "overlap", blame: ["a", "b"], order: ["a", "b"], gaps: [], slack: 0, used: 0 },
  "two members sharing bytes are both blamed",
);
assert.deepEqual(
  planArchiveIndex([["a", 0, 5], ["b", 5, 4]], 20),
  { fault: "", blame: [], order: ["a", "b"], gaps: [], slack: 11, used: 9 },
  "one member ending where the next begins is no clash",
);
assert.deepEqual(
  planArchiveIndex([["big", 2, 5], ["small", 2, 1]], 20),
  { fault: "overlap", blame: ["small", "big"], order: ["small", "big"], gaps: [], slack: 0, used: 0 },
  "at one offset the shorter member is read first",
);
assert.deepEqual(
  planArchiveIndex([["zed", 2, 0], ["ann", 2, 0]], 20),
  { fault: "", blame: [], order: ["ann", "zed"], gaps: [], slack: 20, used: 0 },
  "members level on offset and length are read by name",
);
assert.deepEqual(
  planArchiveIndex([["a", 0, 9], ["b", 3, 20]], 10),
  { fault: "truncated", blame: ["b"], order: ["a", "b"], gaps: [], slack: 0, used: 0 },
  "a member that both overruns and clashes is called truncated",
);

assert.throws(() => planArchiveIndex("no", 4), Error, "an index that is not a list is refused");
assert.throws(() => planArchiveIndex([], -1), Error, "a negative archive size is refused");
assert.throws(() => planArchiveIndex([], 2.5), Error, "a fractional archive size is refused");
assert.throws(() => planArchiveIndex([["a", 0]], 4), Error, "an entry that is not a triple is refused");
assert.throws(() => planArchiveIndex([["", 0, 1]], 4), Error, "an empty name is refused");
assert.throws(() => planArchiveIndex([[7, 0, 1]], 4), Error, "a name that is not a string is refused");
assert.throws(() => planArchiveIndex([["a", 0, 1], ["a", 2, 1]], 4), Error, "one name carried twice is refused");
assert.throws(() => planArchiveIndex([["a", -1, 1]], 4), Error, "a negative offset is refused");
assert.throws(() => planArchiveIndex([["a", 0.5, 1]], 4), Error, "a fractional offset is refused");
assert.throws(() => planArchiveIndex([["a", 0, -1]], 4), Error, "a negative length is refused");
assert.throws(() => planArchiveIndex([["a", 0, 1.5]], 4), Error, "a fractional length is refused");
console.log("ok");
