import assert from "node:assert/strict";
import { factorial } from "./solution.ts";

assert.equal(factorial(0), 1, "the base case the bug missed");
assert.equal(factorial(1), 1, "one");
assert.equal(factorial(5), 120, "the ordinary case still works");
assert.equal(factorial(10), 3628800, "a larger value");

assert.throws(() => factorial(-1), Error, "negative throws rather than recursing");
assert.throws(() => factorial(2.5), Error, "non-integer throws rather than recursing");
