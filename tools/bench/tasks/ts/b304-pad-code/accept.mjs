import assert from "node:assert/strict";
import { padCode } from "./solution.ts";

assert.equal(padCode("7", 3), "007", "padded on the left");
assert.equal(padCode("123", 3), "123", "already the right width");
assert.equal(padCode("1234", 3), "1234", "wider than asked for");
assert.equal(padCode("", 2), "00", "an empty code is all padding");
assert.equal(padCode("ab", 4), "00ab", "letters are padded too");
assert.equal(padCode("9", 1), "9", "no room to pad");
console.log("ok");
