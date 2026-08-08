import assert from "node:assert/strict";
import { normalizeHostname } from "./solution.ts";

assert.equal(normalizeHostname("Example.COM"), "example.com", "lowercased");
assert.equal(normalizeHostname("example.com."), "example.com", "trailing dot drops");
assert.equal(normalizeHostname("a.b-c.d0"), "a.b-c.d0", "hyphens and digits pass");
assert.equal(normalizeHostname("X"), "x", "single label");
assert.equal(
  normalizeHostname("a".repeat(63) + ".io"),
  "a".repeat(63) + ".io",
  "63-character label is the maximum",
);
assert.throws(
  () => normalizeHostname("a".repeat(64) + ".io"),
  Error,
  "64-character label is rejected",
);
assert.throws(
  () => normalizeHostname(("a".repeat(63) + ".").repeat(4)),
  Error,
  "name longer than 253 characters is rejected",
);
assert.throws(() => normalizeHostname(""), Error, "empty name is rejected");
assert.throws(() => normalizeHostname("a..b"), Error, "empty label is rejected");
assert.throws(() => normalizeHostname("a.."), Error, "two trailing dots rejected");
assert.throws(() => normalizeHostname("-a.com"), Error, "leading hyphen rejected");
assert.throws(() => normalizeHostname("a-.com"), Error, "trailing hyphen rejected");
assert.throws(() => normalizeHostname("a_b.com"), Error, "underscore rejected");
assert.throws(() => normalizeHostname("exa mple.com"), Error, "space rejected");
assert.throws(() => normalizeHostname(9), Error, "non-string rejected");
console.log("ok");
