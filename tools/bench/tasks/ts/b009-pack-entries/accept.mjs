import assert from "node:assert/strict";
import { packEntries } from "./solution.ts";

assert.equal(packEntries([["host", "alpha"]]), "host=alpha", "a single plain pair");
assert.equal(packEntries([["a", "1"], ["b", "2"]]), "a=1;b=2", "pairs keep their order");
assert.equal(packEntries([["k;1", "a=b"]]), "k\\;1=a\\=b", "separators inside are escaped");
assert.equal(packEntries([["path", "c:\\tmp"]]), "path=c:\\\\tmp", "a backslash is escaped");
assert.equal(packEntries([["list", "x;y"]]), "list=x\\;y", "a semicolon is escaped");
assert.equal(packEntries([["empty", ""]]), "empty=", "an empty value is allowed");
assert.equal(packEntries([]), "", "no pairs yield the empty string");
assert.throws(() => packEntries([["", "v"]]), Error, "an empty key is rejected");
assert.throws(() => packEntries([["a", "1"], ["a", "2"]]), Error, "a repeated key is rejected");
assert.throws(() => packEntries([["a", 5]]), Error, "a non-string value is rejected");
assert.throws(() => packEntries([["only"]]), Error, "a one-element entry is rejected");
assert.throws(() => packEntries("a=1"), Error, "a non-list argument is rejected");
console.log("ok");
