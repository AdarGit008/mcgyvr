import assert from "node:assert/strict";
import { readSexpr } from "./solution.ts";

assert.equal(readSexpr("42"), 42, "bare integer");
assert.equal(readSexpr("-7"), -7, "negative integer");
assert.equal(readSexpr("hello"), "hello", "bare symbol");
assert.equal(readSexpr(" + "), "+", "operator symbol with padding");
assert.deepEqual(readSexpr("()"), [], "empty list");
assert.deepEqual(readSexpr("(add 1 2)"), ["add", 1, 2], "flat list");
assert.deepEqual(
  readSexpr("(add 1 (mul -2 30))"),
  ["add", 1, ["mul", -2, 30]],
  "nested list",
);
assert.deepEqual(readSexpr("  ( a\t( b ) )\n"), ["a", ["b"]], "free whitespace");
assert.deepEqual(readSexpr("(- 9 3)"), ["-", 9, 3], "lone minus is a symbol");
assert.throws(() => readSexpr(""), Error, "empty input is rejected");
assert.throws(() => readSexpr("   "), Error, "whitespace-only input is rejected");
assert.throws(() => readSexpr("(a"), Error, "unclosed list is rejected");
assert.throws(() => readSexpr(")"), Error, "stray close is rejected");
assert.throws(() => readSexpr("(a) b"), Error, "trailing content is rejected");
assert.throws(() => readSexpr("(1x)"), Error, "digit-led non-integer is rejected");
assert.throws(() => readSexpr("(a,b)"), Error, "character outside the set");
assert.throws(() => readSexpr(42), Error, "non-string is rejected");
console.log("ok");
