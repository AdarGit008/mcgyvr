import assert from "node:assert/strict";
import { overlapAny } from "./solution.ts";

assert.equal(overlapAny([[1, 5], [4, 8]]), true, "the two run into each other");
assert.equal(overlapAny([[1, 4], [4, 8]]), false, "touching is not overlapping");
assert.equal(overlapAny([[1, 2], [5, 6]]), false, "well apart");
assert.equal(overlapAny([]), false, "no bookings at all");
assert.equal(overlapAny([[1, 9]]), false, "one booking cannot overlap");
assert.equal(overlapAny([[1, 2], [5, 6], [5, 7]]), true, "the later pair overlaps");
console.log("ok");
