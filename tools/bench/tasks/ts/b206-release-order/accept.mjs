import assert from "node:assert/strict";
import { orderReleaseTags } from "./solution.ts";

assert.deepEqual(orderReleaseTags(["v1.10.0", "v1.9.3"]), ["v1.9.3", "v1.10.0"], "version fields compare as numbers");
assert.deepEqual(orderReleaseTags(["v2.0.0", "v2.0.0-rc1"]), ["v2.0.0-rc1", "v2.0.0"], "a preview comes before its release");
assert.deepEqual(orderReleaseTags(["v3.1.0-rc10", "v3.1.0-rc2"]), ["v3.1.0-rc2", "v3.1.0-rc10"], "preview numbers compare as numbers");
assert.deepEqual(orderReleaseTags(["v4.0.0-beta1", "v4.0.0-alpha9"]), ["v4.0.0-alpha9", "v4.0.0-beta1"], "preview words compare alphabetically");
assert.deepEqual(orderReleaseTags(["v0.2.1", "v0.10.0", "v0.2.10"]), ["v0.2.1", "v0.2.10", "v0.10.0"], "minor outranks patch");
const given = ["v2.0.0", "v1.0.0"];
assert.deepEqual(orderReleaseTags(given), ["v1.0.0", "v2.0.0"], "the ordered tags come back");
assert.deepEqual(given, ["v2.0.0", "v1.0.0"], "the given list is left untouched");
assert.deepEqual(orderReleaseTags([]), [], "an empty list stays empty");
console.log("ok");
