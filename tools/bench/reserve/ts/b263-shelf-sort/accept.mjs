import assert from "node:assert/strict";
import { shelfSort } from "./solution.ts";

assert.deepEqual(shelfSort(["row9", "row10"]), ["row9", "row10"], "already in order");
assert.deepEqual(shelfSort(["row10", "row9"]), ["row9", "row10"], "ten follows nine");
assert.deepEqual(shelfSort(["bin2", "bin1"]), ["bin1", "bin2"], "a plain swap");
assert.deepEqual(shelfSort([]), [], "nothing to sort");
assert.deepEqual(shelfSort(["a1"]), ["a1"], "a single label");
assert.deepEqual(
  shelfSort(["x3", "y3", "w3"]),
  ["x3", "y3", "w3"],
  "equal numbers keep their arrival order",
);
console.log("ok");
