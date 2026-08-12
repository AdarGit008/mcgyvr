import assert from "node:assert/strict";
import { addOne, mergeTally } from "./solution.ts";

assert.deepEqual(addOne({ a: 1 }, "a", 2), { a: 3 }, "added to an existing name");
assert.deepEqual(addOne({}, "a", 1), { a: 1 }, "a new name starts at nothing");
assert.deepEqual(mergeTally({ a: 1 }, { b: 2 }), { a: 1, b: 2 }, "no name is shared");
assert.deepEqual(mergeTally({ a: 1 }, { a: 2 }), { a: 3 }, "a shared name adds up");
assert.deepEqual(mergeTally({}, {}), {}, "two empty tallies");

const source = { a: 1 };
addOne(source, "a", 5);
assert.deepEqual(source, { a: 1 }, "the tally it was given is unchanged");
console.log("ok");
