import assert from "node:assert/strict";
import { truncate } from "./solution.ts";

assert.equal(truncate("hello", 5), "hello", "exactly at the limit is returned whole");
assert.equal(truncate("hello", 10), "hello", "shorter than the limit");
assert.equal(truncate("hello world", 8), "hello...", "longer is cut to exactly the limit");
assert.equal(truncate("hello world", 8).length, 8, "the result is exactly limit characters");
assert.equal(truncate("abcdef", 3), "...", "the smallest legal limit");
assert.equal(truncate("", 5), "", "empty string");
assert.equal(truncate("abcd", 4), "abcd", "boundary: length equals limit");
assert.equal(truncate("abcde", 4), "a...", "boundary: one past the limit");

for (const bad of [2, -1, 3.5, "5"]) {
  assert.throws(() => truncate("hello", bad), Error, `limit ${JSON.stringify(bad)} throws`);
}
