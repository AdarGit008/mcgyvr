import assert from "node:assert/strict";
import { maskAccount } from "./solution.ts";

assert.equal(maskAccount("12345678", 4), "****5678", "plain digits");
assert.equal(maskAccount("1234-5678-9012", 4), "****-****-9012", "hyphen groups");
assert.equal(
  maskAccount("1234 5678 9012 3456", 4),
  "**** **** **** 3456",
  "space groups",
);
assert.equal(maskAccount("007", 3), "007", "exactly keep digits is unchanged");
assert.equal(maskAccount("9-87", 1), "*-*7", "keep of one");
assert.throws(() => maskAccount(42, 4), Error, "non-string account is rejected");
assert.throws(() => maskAccount("", 4), Error, "empty account is rejected");
assert.throws(() => maskAccount("12a4", 2), Error, "illegal character is rejected");
assert.throws(() => maskAccount("-123", 2), Error, "leading separator is rejected");
assert.throws(() => maskAccount("12--34", 2), Error, "adjacent separators are rejected");
assert.throws(() => maskAccount("1234", 0), Error, "keep below one is rejected");
assert.throws(() => maskAccount("123", 4), Error, "fewer digits than keep is rejected");
console.log("ok");
