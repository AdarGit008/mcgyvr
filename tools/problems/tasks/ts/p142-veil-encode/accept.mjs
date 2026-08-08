import assert from "node:assert/strict";
import { veilEncode } from "./solution.ts";

assert.equal(veilEncode("march", "bad cab"), "amc rma", "worked example");
assert.equal(veilEncode("crystal", "the mixer hums"), "izt qxetk zhqj", "longer keyword");
assert.equal(veilEncode("z", "az za"), "za az", "single-letter keyword swaps ends");
assert.equal(veilEncode("quartz", "pack my box"), "lqas oc umd", "mid-alphabet keyword");
assert.equal(veilEncode("banana", "abn"), "bap", "keyword repeats are skipped");
assert.equal(veilEncode("veil", "veil code"), "fzur iolz", "keyword letters map first");
assert.equal(veilEncode("march", ""), "", "empty message encodes to empty");
assert.throws(() => veilEncode("", "hi"), Error, "empty keyword is rejected");
assert.throws(() => veilEncode("Big", "hi"), Error, "uppercase keyword is rejected");
assert.throws(() => veilEncode("k1", "hi"), Error, "digit in keyword is rejected");
assert.throws(() => veilEncode("key", "Hi"), Error, "uppercase message is rejected");
assert.throws(() => veilEncode("key", 5), Error, "non-string message is rejected");
console.log("ok");
