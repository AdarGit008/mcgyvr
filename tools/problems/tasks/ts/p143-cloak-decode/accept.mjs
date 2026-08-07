import assert from "node:assert/strict";
import { cloakDecode } from "./solution.ts";

assert.equal(cloakDecode("orbit", "roi"), "bad", "worked example");
assert.equal(cloakDecode("orbit", "qtbpts jtqqoct"), "secret message", "phrase with space");
assert.equal(cloakDecode("velvet", "osfar dvpemp"), "quiet harbor", "keyword with repeats");
assert.equal(cloakDecode("gadget", "ztaqg lukt"), "zebra mule", "another keyword");
assert.equal(cloakDecode("zed", "zebra"), "abesd", "short keyword");
assert.equal(cloakDecode("ba", "ba"), "ab", "two-letter keyword swaps a and b");
assert.throws(() => cloakDecode("", "roi"), Error, "empty keyword is rejected");
assert.throws(() => cloakDecode("Bad", "roi"), Error, "uppercase keyword is rejected");
assert.throws(() => cloakDecode("orbit", "r2"), Error, "digit in text is rejected");
assert.throws(() => cloakDecode("orbit", 7), Error, "non-string text is rejected");
console.log("ok");
