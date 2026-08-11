import assert from "node:assert/strict";
import { slotPack } from "./solution.ts";

assert.deepEqual(
  slotPack(["a", "b", "c", "d", "e"], 2),
  [["a", "b"], ["c", "d"], ["e"]],
  "a short final slot",
);
assert.deepEqual(slotPack(["a", "b", "c"], 3), [["a", "b", "c"]], "one exact slot");
assert.deepEqual(slotPack([], 2), [], "nothing to pack");
assert.deepEqual(slotPack(["a", "b"], 1), [["a"], ["b"]], "one item per slot");
assert.deepEqual(slotPack(["a", "b"], 5), [["a", "b"]], "capacity to spare");
assert.deepEqual(slotPack(["x", "y", "z"], 2), [["x", "y"], ["z"]], "order is kept");
console.log("ok");
