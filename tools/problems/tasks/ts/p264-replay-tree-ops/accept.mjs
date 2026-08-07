import assert from "node:assert/strict";
import { replayTreeOps } from "./solution.ts";

assert.deepEqual(replayTreeOps([]), [], "no steps leave an empty index");
assert.deepEqual(replayTreeOps(["add:50"]), [50], "one value is its own root");
assert.deepEqual(
  replayTreeOps(["add:50", "add:30", "add:70", "add:20", "add:40", "add:60", "add:80"]),
  [50, 30, 20, 40, 70, 60, 80],
  "a balanced seven value index"
);
assert.deepEqual(
  replayTreeOps(["add:50", "add:30", "add:70", "add:20", "add:40", "add:60", "add:80", "drop:20"]),
  [50, 30, 40, 70, 60, 80],
  "dropping a childless value"
);
assert.deepEqual(
  replayTreeOps(["add:50", "add:30", "add:70", "add:20", "add:40", "add:60", "add:80", "drop:30"]),
  [50, 20, 40, 70, 60, 80],
  "dropping a value with two children pulls up the left side's highest"
);
assert.deepEqual(
  replayTreeOps(["add:50", "add:30", "add:70", "add:20", "add:40", "add:60", "add:80", "drop:50"]),
  [40, 30, 20, 70, 60, 80],
  "dropping the root"
);
assert.deepEqual(replayTreeOps(["add:5", "add:5", "add:5"]), [5], "repeat additions change nothing");
assert.deepEqual(
  replayTreeOps(["add:8", "add:3", "add:10", "add:1", "add:6", "add:4", "add:7", "add:14", "add:13", "drop:8"]),
  [7, 3, 1, 6, 4, 10, 14, 13],
  "the left side's highest is itself a child of something"
);
assert.deepEqual(
  replayTreeOps(["add:-4", "add:-9", "add:0", "add:-2", "drop:-4"]),
  [-9, 0, -2],
  "negative values sort the ordinary way"
);
assert.deepEqual(replayTreeOps(["add:1", "add:2", "add:3", "drop:1", "drop:2"]), [3], "a rightward chain drains");
assert.deepEqual(replayTreeOps(["add:20", "add:10", "add:30", "drop:20", "drop:10", "drop:30"]), [], "everything dropped");
assert.deepEqual(replayTreeOps(["add:9", "drop:9", "add:4", "add:2"]), [4, 2], "an emptied index takes a new root");

assert.throws(() => replayTreeOps("add:5"), Error, "a text argument is not a list");
assert.throws(() => replayTreeOps(["add:5", "grow:6"]), Error, "an unknown verb is rejected");
assert.throws(() => replayTreeOps(["add:x"]), Error, "a value that is not digits is rejected");
assert.throws(() => replayTreeOps(["add"]), Error, "a step with no colon is rejected");
assert.throws(() => replayTreeOps([50]), Error, "a step that is not text is rejected");
assert.throws(() => replayTreeOps(["drop:5"]), Error, "dropping from an empty index is rejected");
assert.throws(() => replayTreeOps(["add:5", "drop:6"]), Error, "dropping an absent value is rejected");
assert.throws(() => replayTreeOps(["add:5", "add:7", "drop:5", "drop:5"]), Error, "dropping the same value twice is rejected");
console.log("ok");
