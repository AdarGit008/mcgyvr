import assert from "node:assert/strict";
import { filePaths, treeBytes, heavyFolders } from "./solution.ts";

const tree = {
  name: "media",
  children: [
    {
      name: "clips",
      children: [
        { name: "intro.mov", bytes: 400 },
        { name: "raw", children: [{ name: "take1.mov", bytes: 3000 }] },
      ],
    },
    { name: "notes.txt", bytes: 50 },
    { name: "empty", children: [] },
  ],
};

assert.deepEqual(
  heavyFolders(tree, 3000),
  [["media", 3450], ["media/clips", 3400], ["media/clips/raw", 3000]],
  "folders at or above the threshold, in walking order",
);
assert.deepEqual(
  heavyFolders(tree, 3001),
  [["media", 3450], ["media/clips", 3400]],
  "a folder exactly one byte short drops out",
);
assert.deepEqual(
  heavyFolders(tree, 0),
  [
    ["media", 3450],
    ["media/clips", 3400],
    ["media/clips/raw", 3000],
    ["media/empty", 0],
  ],
  "threshold zero reports every folder, empty ones included",
);
assert.deepEqual(heavyFolders({ name: "solo.txt", bytes: 5 }, 0), [], "a file root has no folders");
assert.deepEqual(
  filePaths(tree),
  ["media/clips/intro.mov", "media/clips/raw/take1.mov", "media/notes.txt"],
  "file paths in walking order",
);
assert.deepEqual(filePaths({ name: "solo.txt", bytes: 5 }), ["solo.txt"], "a file root is its own path");
assert.equal(treeBytes(tree), 3450, "bytes roll up through every folder");
assert.equal(treeBytes({ name: "empty", children: [] }), 0, "an empty folder holds zero bytes");
assert.throws(() => heavyFolders(42, 0), Error, "non-mapping node rejected");
assert.throws(() => heavyFolders({ name: "", children: [] }, 0), Error, "empty name rejected");
assert.throws(() => heavyFolders({ name: "a/b", children: [] }, 0), Error, "slash in a name rejected");
assert.throws(() => heavyFolders({ name: "x" }, 0), Error, "neither bytes nor children rejected");
assert.throws(
  () => heavyFolders({ name: "x", bytes: 5, children: [] }, 0),
  Error,
  "both bytes and children rejected",
);
assert.throws(() => heavyFolders(tree, -1), Error, "negative threshold rejected");
assert.throws(() => heavyFolders(tree, 2.5), Error, "fractional threshold rejected");
assert.throws(() => filePaths({ name: "x", children: "nope" }), Error, "non-list children rejected");
assert.throws(() => treeBytes({ name: "x", bytes: 1.5 }), Error, "fractional bytes rejected");
console.log("ok");
