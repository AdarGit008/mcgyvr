import assert from "node:assert/strict";
import { scanPairs, parseOption } from "./solution.ts";

assert.deepEqual(scanPairs("mode=fast"), [["mode", "fast"]], "single pair");
assert.deepEqual(
  scanPairs("a=1;b=two;c=3"),
  [["a", "1"], ["b", "two"], ["c", "3"]],
  "several pairs keep input order",
);
assert.deepEqual(
  scanPairs('note="x;y";flag=on'),
  [["note", "x;y"], ["flag", "on"]],
  "a quoted semicolon does not split",
);
assert.deepEqual(scanPairs("label="), [["label", ""]], "bare empty value");
assert.deepEqual(scanPairs('empty=""'), [["empty", ""]], "quoted empty value");
assert.deepEqual(parseOption('depth="3;4"'), ["depth", "3;4"], "helper unquotes");
assert.throws(() => scanPairs(42), Error, "non-string is rejected");
assert.throws(() => scanPairs(""), Error, "empty string is rejected");
assert.throws(() => scanPairs("a=1;;b=2"), Error, "empty segment is rejected");
assert.throws(() => scanPairs("1a=x"), Error, "non-bare key is rejected");
assert.throws(() => scanPairs("dup=1;dup=2"), Error, "repeated key is rejected");
assert.throws(() => scanPairs('q="abc'), Error, "unterminated quote is rejected");
console.log("ok");
