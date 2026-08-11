import assert from "node:assert/strict";
import { overCount } from "./solution.ts";

assert.equal(overCount({ a: 1, b: 5 }, 3), 1, "only the high one counts");
assert.equal(overCount({ a: 3 }, 3), 1, "reaching the floor counts");
assert.equal(overCount({ a: 1 }, 3), 0, "below the floor does not");
assert.equal(overCount({}, 3), 0, "an empty store");
assert.equal(overCount({ a: 5, b: 6 }, 3), 2, "everything counts");
assert.equal(overCount({ a: 1, b: 2 }, 3), 0, "nothing counts");
console.log("ok");
