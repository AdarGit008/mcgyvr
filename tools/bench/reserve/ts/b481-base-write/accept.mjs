import assert from "node:assert/strict";
import { baseWrite } from "./solution.ts";

assert.equal(baseWrite(5, 2), "101", "a count in base two");
assert.equal(baseWrite(255, 16), "ff", "letters carry the values above nine");
assert.equal(baseWrite(8, 8), "10", "a count that rolls to the next place");
assert.equal(baseWrite(9, 10), "9", "a single figure");
assert.equal(baseWrite(0, 2), "0", "a count of nothing");
assert.throws(() => baseWrite(5, 1), Error, "a base below two is rejected");
assert.throws(() => baseWrite(5, 17), Error, "a base above sixteen is rejected");
console.log("ok");
