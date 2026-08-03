import assert from "node:assert/strict";
import { parseCsvLine } from "./solution.ts";

assert.deepEqual(parseCsvLine("a,b,c"), ["a", "b", "c"], "plain fields");
assert.deepEqual(parseCsvLine(""), [""], "empty line is one empty field");
assert.deepEqual(parseCsvLine("a"), ["a"], "single field");
assert.deepEqual(parseCsvLine("a,,c"), ["a", "", "c"], "empty field in the middle");
assert.deepEqual(parseCsvLine("a,b,"), ["a", "b", ""], "trailing empty field");
assert.deepEqual(parseCsvLine(',a'), ["", "a"], "leading empty field");
assert.deepEqual(parseCsvLine('"a,b",c'), ["a,b", "c"], "comma inside a quoted field");
assert.deepEqual(parseCsvLine('"say ""hi""",x'), ['say "hi"', "x"], "doubled quote is one quote");
assert.deepEqual(parseCsvLine('""'), [""], "an empty quoted field");
assert.deepEqual(parseCsvLine(' a , b '), [" a ", " b "], "unquoted spaces are kept");
assert.deepEqual(parseCsvLine('"a"'), ["a"], "quotes are stripped from a quoted field");

assert.throws(() => parseCsvLine('"unterminated'), Error, "unclosed quote throws");
