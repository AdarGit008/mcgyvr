import assert from "node:assert/strict";
import { trimTo } from "./solution.ts";

assert.equal(trimTo("abcdefgh", 5), "ab...", "the dots count toward the limit");
assert.equal(trimTo("abc", 5), "abc", "already short enough");
assert.equal(trimTo("abcde", 5), "abcde", "exactly on the limit");
assert.equal(trimTo("abcdef", 5), "ab...", "one over the limit");
assert.equal(trimTo("", 10), "", "an empty line");
assert.throws(() => trimTo("abc", 3), Error, "a limit under four is rejected");
console.log("ok");
