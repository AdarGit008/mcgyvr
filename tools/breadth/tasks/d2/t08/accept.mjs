import assert from "node:assert/strict";
import { parseCsvLine } from "./solution.ts";

assert.deepEqual(parseCsvLine(""), [""], "empty line is one empty field");
assert.deepEqual(parseCsvLine("a,b,c"), ["a", "b", "c"], "plain fields");
assert.deepEqual(parseCsvLine("a,,b"), ["a", "", "b"], "empty middle field");
assert.deepEqual(parseCsvLine("a,"), ["a", ""], "trailing comma means empty last field");
assert.deepEqual(parseCsvLine(",a"), ["", "a"], "leading comma means empty first field");
assert.deepEqual(parseCsvLine(",,"), ["", "", ""], "only commas");
assert.deepEqual(parseCsvLine('"a,b",c'), ["a,b", "c"], "comma inside quoted field");
assert.deepEqual(parseCsvLine('"say ""hi""",x'), ['say "hi"', "x"], "doubled quotes decode");
assert.deepEqual(parseCsvLine('""'), [""], "quoted empty field");
assert.deepEqual(parseCsvLine('""""'), ['"'], "field that is one literal quote");
assert.deepEqual(parseCsvLine(" a , b "), [" a ", " b "], "spaces are never trimmed");
assert.deepEqual(parseCsvLine('a,"b",c'), ["a", "b", "c"], "quoted field mid-line");

assert.throws(() => parseCsvLine(42), Error, "non-string throws");
assert.throws(() => parseCsvLine('"unterminated'), Error, "unterminated quote throws");
assert.throws(() => parseCsvLine('"a"x,b'), Error, "junk after closing quote throws");
assert.throws(() => parseCsvLine('a"b,c'), Error, "quote inside unquoted field throws");
