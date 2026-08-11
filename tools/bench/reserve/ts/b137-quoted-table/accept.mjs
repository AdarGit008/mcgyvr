import assert from "node:assert/strict";
import { parseQuotedTable } from "./solution.ts";

assert.deepEqual(parseQuotedTable("a,b\nc,d"), [["a", "b"], ["c", "d"]], "plain rows");
assert.deepEqual(parseQuotedTable("note"), [["note"]], "one bare field");
assert.deepEqual(parseQuotedTable('"a,b",c'), [["a,b", "c"]], "comma inside quotes");
assert.deepEqual(
  parseQuotedTable('"say ""hi""",x'),
  [['say "hi"', "x"]],
  "doubled quote becomes one literal quote",
);
assert.deepEqual(
  parseQuotedTable('"line one\nline two",z\nq,r'),
  [["line one\nline two", "z"], ["q", "r"]],
  "newline inside quotes stays in the field",
);
assert.deepEqual(parseQuotedTable("a,,c"), [["a", "", "c"]], "empty field between commas");
assert.deepEqual(parseQuotedTable('"",b'), [["", "b"]], "quoted empty field");
assert.deepEqual(parseQuotedTable("a,b\n"), [["a", "b"]], "one final newline opens no row");
assert.deepEqual(parseQuotedTable(",\n,"), [["", ""], ["", ""]], "rows of empty fields");
assert.deepEqual(parseQuotedTable('"a"\nb'), [["a"], ["b"]], "quoted equals unquoted");
assert.throws(() => parseQuotedTable(42), Error, "non-string is rejected");
assert.throws(() => parseQuotedTable(""), Error, "empty text is rejected");
assert.throws(() => parseQuotedTable("a\rb"), Error, "carriage return is rejected");
assert.throws(() => parseQuotedTable('a"b,c'), Error, "quote in unquoted field is rejected");
assert.throws(() => parseQuotedTable('"abc'), Error, "unclosed quote is rejected");
assert.throws(() => parseQuotedTable('"a"x,b'), Error, "junk after closing quote is rejected");
assert.throws(() => parseQuotedTable("a,b\nc"), Error, "ragged row is rejected");
console.log("ok");
