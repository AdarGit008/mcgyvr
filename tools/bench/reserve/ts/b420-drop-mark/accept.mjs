import assert from "node:assert/strict";
import { dropMark } from "./solution.ts";

assert.equal(dropMark("a-b-c", "-"), "abc", "the dashes go");
assert.equal(dropMark("abc", "-"), "abc", "nothing to remove");
assert.equal(dropMark("", "-"), "", "an empty text");
assert.equal(dropMark("---", "-"), "", "everything goes");
assert.equal(dropMark("a", "a"), "", "the only character goes");
assert.equal(dropMark("aXbXc", "X"), "abc", "a capital marker");
console.log("ok");
