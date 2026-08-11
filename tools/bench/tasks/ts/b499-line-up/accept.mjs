import assert from "node:assert/strict";
import { lineUp } from "./solution.ts";

assert.deepEqual(lineUp({ b: "a" }, "b"), ["b", "a"], "one step up the line");
assert.deepEqual(lineUp({ c: "b", b: "a" }, "c"), ["c", "b", "a"], "the line runs to the top");
assert.deepEqual(lineUp({ b: "a" }, "a"), ["a"], "a name with nobody above it");
assert.deepEqual(lineUp({ b: "a" }, "z"), ["z"], "a name the book does not know");
assert.deepEqual(lineUp({}, "a"), ["a"], "a book holding no links");
assert.throws(() => lineUp({ a: "b", b: "a" }, "a"), Error, "links running in a circle are rejected");
console.log("ok");
