import assert from "node:assert/strict";
import { decodeEscapedNote } from "./solution.ts";

assert.equal(decodeEscapedNote("meet the courier at nine"), "meet the courier at nine", "a note without escapes is unchanged");
assert.equal(decodeEscapedNote("50=25 off, tea =26 buns"), "50% off, tea & buns", "escapes stand for their characters");
assert.equal(decodeEscapedNote("the crate held car=\nrots"), "the crate held carrots", "a trailing equals folds the next line on");
assert.equal(decodeEscapedNote("first row   \nsecond row"), "first row\nsecond row", "trailing blanks vanish and the break stays");
assert.equal(decodeEscapedNote("keep me=20\nnext"), "keep me \nnext", "an escaped space outlives the trimming pass");
assert.equal(decodeEscapedNote(""), "", "an empty note decodes to nothing");
assert.throws(() => decodeEscapedNote("=G1 crates"), Error, "an escape that is not two hex digits is rejected");
console.log("ok");
