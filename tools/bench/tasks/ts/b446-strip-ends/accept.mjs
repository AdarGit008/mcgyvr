import assert from "node:assert/strict";
import { stripEnds } from "./solution.ts";

assert.equal(stripEnds("--a--", "-"), "a", "several from each end");
assert.equal(stripEnds("-a-", "-"), "a", "one from each end");
assert.equal(stripEnds("a", "-"), "a", "nothing to strip");
assert.equal(stripEnds("---", "-"), "", "everything is stripped");
assert.equal(stripEnds("", "-"), "", "an empty text");
assert.equal(stripEnds("--a", "-"), "a", "only the front carries them");
console.log("ok");
