import assert from "node:assert/strict";
import { packClueLine } from "./solution.ts";

assert.equal(packClueLine(7, []), ".......", "no clues draws a bare width");
assert.equal(packClueLine(7, [3]), "###....", "one group hugs the left edge");
assert.equal(packClueLine(7, [2, 1]), "##.#...", "one dot parts the two groups");
assert.equal(packClueLine(7, [1, 1, 1]), "#.#.#..", "three lone cells and their gaps");
assert.equal(packClueLine(7, [7]), "#######", "a group filling the whole width");
assert.equal(packClueLine(5, [2, 2]), "##.##", "a drawing that ends exactly at the edge");
assert.equal(packClueLine(1, [1]), "#", "a width of one");
assert.equal(packClueLine(9, [4, 2]), "####.##..", "the leftover tail is dots");
assert.throws(() => packClueLine(0, [1]), Error, "a width of zero is rejected");
assert.throws(() => packClueLine(2.5, [1]), Error, "a fractional width is rejected");
assert.throws(() => packClueLine(7, [0]), Error, "a clue of zero is rejected");
assert.throws(() => packClueLine(4, [2, 2]), Error, "a drawing wider than the line");
assert.throws(() => packClueLine(7, "3"), Error, "a clue list that is not a list");
assert.throws(() => packClueLine(7, ["3"]), Error, "a clue that is not a number");
console.log("ok");
