import assert from "node:assert/strict";
import { unwrapLabel } from "./solution.ts";

assert.equal(unwrapLabel("[a]"), "a", "a matching pair is removed");
assert.equal(unwrapLabel("[a"), "[a", "an unclosed bracket is left alone");
assert.equal(unwrapLabel("a"), "a", "no brackets at all");
assert.equal(unwrapLabel("[]"), "", "an empty pair");
assert.equal(unwrapLabel(""), "", "an empty label");
assert.equal(unwrapLabel("[ab]"), "ab", "a longer label");
console.log("ok");
