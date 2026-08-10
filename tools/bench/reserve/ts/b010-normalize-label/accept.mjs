import assert from "node:assert/strict";
import { normalizeLabel } from "./solution.ts";

assert.equal(normalizeLabel("Alpha"), "alpha", "a clean word is lowercased");
assert.equal(normalizeLabel("  Team  Alpha  "), "team-alpha", "surrounding space trims, runs collapse");
assert.equal(normalizeLabel("build_42_final"), "build-42-final", "underscores become hyphens");
assert.equal(normalizeLabel("- retry -- now -"), "retry-now", "mixed separator runs collapse");
assert.equal(normalizeLabel("release-2-0"), "release-2-0", "an already-clean label is unchanged");
assert.equal(normalizeLabel("a".repeat(32)), "a".repeat(32), "a 32-character label is allowed");
assert.throws(() => normalizeLabel("a".repeat(33)), Error, "a 33-character label is rejected");
assert.throws(() => normalizeLabel("café"), Error, "a non-ASCII character is rejected");
assert.throws(() => normalizeLabel("   "), Error, "whitespace only is rejected");
assert.throws(() => normalizeLabel("_-_"), Error, "separators only are rejected");
assert.throws(() => normalizeLabel(42), Error, "a non-string argument is rejected");
assert.throws(() => normalizeLabel("  New "), Error, "a reserved name is rejected");
console.log("ok");
