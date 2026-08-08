import assert from "node:assert/strict";
import { staffedPosts } from "./solution.ts";

assert.equal(staffedPosts([[0, 1], [0]], 2), 2, "first applicant must be moved along");
assert.equal(staffedPosts([[0], [0, 1], [1, 2], [2]], 3), 3, "chain of reassignments");
assert.equal(staffedPosts([[0, 1], [1, 2], [0, 2]], 3), 3, "everyone fits");
assert.equal(staffedPosts([[0], [0], [0]], 2), 1, "one post cannot take three");
assert.equal(staffedPosts([], 3), 0, "no applicants staffs nothing");
assert.equal(staffedPosts([[], [1]], 2), 1, "an applicant with no posts sits out");
assert.equal(
  staffedPosts([[0, 1], [0, 2], [0, 3], [0]], 4),
  4,
  "the picky applicant displaces a whole cascade",
);
assert.equal(staffedPosts([[1, 2], [0, 1], [0], [2], [2, 3]], 4), 4, "dense overlap");
assert.throws(() => staffedPosts([[0]], 0), Error, "zero posts rejected");
assert.throws(() => staffedPosts([[0]], 2.5), Error, "fractional posts rejected");
assert.throws(() => staffedPosts([[7]], 3), Error, "out-of-range post rejected");
assert.throws(() => staffedPosts([[-1]], 3), Error, "negative post rejected");
assert.throws(() => staffedPosts([[0.5]], 3), Error, "fractional post rejected");
console.log("ok");
