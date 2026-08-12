import assert from "node:assert/strict";
import { joinBooks } from "./solution.ts";

assert.deepEqual(joinBooks({ a: 1 }, { b: 2 }), { a: 1, b: 2 }, "names standing apart");
assert.deepEqual(joinBooks({ a: 1 }, { a: 1 }), { a: 1 }, "a name agreeing in both");
assert.deepEqual(joinBooks({}, { b: 2 }), { b: 2 }, "a first book holding nothing");
assert.deepEqual(joinBooks({ a: 1 }, {}), { a: 1 }, "a second book holding nothing");
assert.deepEqual(joinBooks({}, {}), {}, "two books holding nothing");
assert.throws(() => joinBooks({ a: 1 }, { a: 2 }), Error, "a name disagreeing is rejected");
console.log("ok");
