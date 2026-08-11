import assert from "node:assert/strict";
import { spillLots } from "./solution.ts";

assert.deepEqual(spillLots([["a", "b"], ["c"]]), ["a", "b", "c"], "lots tip out in order");
assert.deepEqual(spillLots([["a", ""], ["b"]]), ["a", "b"], "an entry holding nothing is left behind");
assert.deepEqual(spillLots([[], ["c"]]), ["c"], "a lot holding nothing adds nothing");
assert.deepEqual(spillLots([["a"], ["a"]]), ["a", "a"], "the same entry in two lots");
assert.deepEqual(spillLots([[]]), [], "one lot holding nothing");
assert.deepEqual(spillLots([]), [], "no lots at all");
console.log("ok");
