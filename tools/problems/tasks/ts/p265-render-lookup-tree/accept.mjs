import assert from "node:assert/strict";
import { renderLookupTree } from "./solution.ts";

assert.equal(renderLookupTree([], []), ".", "nothing planted draws a lone dot");
assert.equal(renderLookupTree([7], []), "[7|.|.]", "a single cell");
assert.equal(renderLookupTree([7, 3, 9], []), "[7|[3|.|.]|[9|.|.]]", "two leaves under a root");
assert.equal(renderLookupTree([7, 3, 9], [3]), "[7|.|[9|.|.]]", "pulling a leaf");
assert.equal(
  renderLookupTree([7, 3, 9, 1, 5], [3]),
  "[7|[5|[1|.|.]|.]|[9|.|.]]",
  "pulling a cell whose high side is a single value"
);
assert.equal(
  renderLookupTree([7, 3, 9, 8, 12, 10], [9]),
  "[7|[3|.|.]|[10|[8|.|.]|[12|.|.]]]",
  "the stand-in comes from deeper in the high side"
);
assert.equal(
  renderLookupTree([7, 3, 9, 8, 12, 10], [7]),
  "[8|[3|.|.]|[9|.|[12|[10|.|.]|.]]]",
  "pulling the root"
);
assert.equal(
  renderLookupTree([50, 30, 70, 60, 65, 80], [50]),
  "[60|[30|.|.]|[70|[65|.|.]|[80|.|.]]]",
  "the stand-in leaves a child behind it"
);
assert.equal(
  renderLookupTree([10, 5, 15, 12, 20, 11, 13], [10]),
  "[11|[5|.|.]|[15|[12|.|[13|.|.]]|[20|.|.]]]",
  "a deeper stand-in with a high child of its own"
);
assert.equal(
  renderLookupTree([-3, -8, 0, -5], [-3]),
  "[0|[-8|.|[-5|.|.]]|.]",
  "negative values plant and pull alike"
);
assert.equal(renderLookupTree([4, 4, 4, 2], []), "[4|[2|.|.]|.]", "repeats of a planted value are ignored");
assert.equal(renderLookupTree([5, 2, 8], [5, 2, 8]), ".", "pulling everything empties the tree");

assert.throws(() => renderLookupTree(7, []), Error, "a first argument that is not a list");
assert.throws(() => renderLookupTree([7], "3"), Error, "a second argument that is not a list");
assert.throws(() => renderLookupTree([7, 1.5], []), Error, "a fractional planted value");
assert.throws(() => renderLookupTree(["7"], []), Error, "a planted value that is text");
assert.throws(() => renderLookupTree([7, 3], [9]), Error, "pulling a value never planted");
assert.throws(() => renderLookupTree([7, 3], [3, 3]), Error, "pulling the same value twice");
assert.throws(() => renderLookupTree([], [1]), Error, "pulling from an empty tree");
console.log("ok");
