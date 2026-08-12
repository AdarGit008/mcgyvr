import assert from "node:assert/strict";
import { hexSplit, hexJoin } from "./solution.ts";

assert.deepEqual(hexSplit("#aabbcc"), ["aa", "bb", "cc"], "three parts in order");
assert.deepEqual(hexSplit("#ABCDEF"), ["AB", "CD", "EF"], "upper case is kept");
assert.throws(() => hexSplit("#abc"), Error, "too few digits");
assert.throws(() => hexSplit("aabbcc"), Error, "the hash is required");
assert.equal(hexJoin(["AA", "BB", "CC"]), "#aabbcc", "joined and lower-cased");
assert.equal(hexJoin(["00", "00", "00"]), "#000000", "all zeroes");
console.log("ok");
