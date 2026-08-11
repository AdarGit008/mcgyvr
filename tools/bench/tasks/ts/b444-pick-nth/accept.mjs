import assert from "node:assert/strict";
import { pickNth } from "./solution.ts";

assert.equal(pickNth(["a", "b", "c"], 1), "a", "the first place");
assert.equal(pickNth(["a", "b", "c"], 3), "c", "the last place");
assert.equal(pickNth(["a"], 0), "", "there is no place nought");
assert.equal(pickNth(["a"], 2), "", "past the end of the list");
assert.equal(pickNth([], 1), "", "an empty list");
assert.equal(pickNth(["x", "y"], 2), "y", "the second place");
console.log("ok");
