import assert from "node:assert/strict";
import { parcelGirth, parcelOversize } from "./solution.ts";

assert.equal(parcelGirth(2, 3), 10, "twice each side, added");
assert.equal(parcelGirth(0, 0), 0, "a flat parcel has no girth");
assert.equal(parcelOversize(10, 2, 3, 25), false, "under the limit");
assert.equal(parcelOversize(10, 2, 3, 15), true, "over the limit");
assert.equal(parcelOversize(5, 0, 0, 5), false, "exactly at the limit is allowed");
assert.equal(parcelOversize(6, 0, 0, 5), true, "one unit past the limit");
console.log("ok");
