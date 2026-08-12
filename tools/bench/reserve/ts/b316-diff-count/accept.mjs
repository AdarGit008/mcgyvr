import assert from "node:assert/strict";
import { diffCount } from "./solution.ts";

assert.equal(diffCount([1, 2, 3], [1, 9, 3]), 1, "one position differs");
assert.equal(diffCount([1, 2], [1, 2]), 0, "the same list twice");
assert.equal(diffCount([1, 2, 3], [1, 2]), 1, "an extra position counts");
assert.equal(diffCount([], []), 0, "two empty lists");
assert.equal(diffCount([], [1, 2]), 2, "every position is extra");
assert.equal(diffCount([1, 2], [3, 4]), 2, "nothing matches");
console.log("ok");
