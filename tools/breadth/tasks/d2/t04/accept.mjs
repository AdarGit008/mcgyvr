import assert from "node:assert/strict";
import { tokenize } from "./solution.ts";

assert.deepEqual(tokenize(""), [], "empty string");
assert.deepEqual(tokenize("   \t "), [], "only separators");
assert.deepEqual(tokenize("one two\tthree"), ["one", "two", "three"], "plain split");
assert.deepEqual(tokenize("  lead trail  "), ["lead", "trail"], "leading/trailing separators");
assert.deepEqual(tokenize('"hello world"'), ["hello world"], "quoted space stays");
assert.deepEqual(tokenize('a"b c"d'), ["ab cd"], "quoted section glues to neighbors");
assert.deepEqual(tokenize('""'), [""], "empty quotes make an empty token");
assert.deepEqual(tokenize('x "" y'), ["x", "", "y"], "empty token between words");
assert.deepEqual(tokenize("a\\ b"), ["a b"], "escaped space joins a token");
assert.deepEqual(tokenize('say \\"hi\\"'), ["say", '"hi"'], "escaped quotes are literal");
assert.deepEqual(tokenize("back\\\\slash"), ["back\\slash"], "escaped backslash");
assert.deepEqual(tokenize('"in \\" quote"'), ['in " quote'], "escape works inside quotes");
assert.deepEqual(tokenize('"tab\there"'), ["tab\there"], "tab inside quotes is literal");

assert.throws(() => tokenize('"unterminated'), Error, "unterminated quote throws");
assert.throws(() => tokenize("oops\\"), Error, "trailing backslash throws");
