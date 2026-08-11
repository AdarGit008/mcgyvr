import assert from "node:assert/strict";
import { sortByLen } from "./solution.ts";

assert.deepEqual(sortByLen(["ccc", "a", "bb"]), ["a", "bb", "ccc"], "shortest first");
assert.deepEqual(sortByLen(["bb", "aa"]), ["aa", "bb"], "a tie goes alphabetically");
assert.deepEqual(sortByLen([]), [], "no words at all");
assert.deepEqual(sortByLen(["one"]), ["one"], "a single word");
assert.deepEqual(sortByLen(["b", "a", "cc"]), ["a", "b", "cc"], "ties then length");

const source = ["bb", "a"];
sortByLen(source);
assert.deepEqual(source, ["bb", "a"], "the list it was given is untouched");
console.log("ok");
