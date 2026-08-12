import assert from "node:assert/strict";
import { dropBlank } from "./solution.ts";

assert.deepEqual(dropBlank(["a", "", "b"]), ["a", "b"], "the empty one goes");
assert.deepEqual(dropBlank(["a", " ", "b"]), ["a", " ", "b"], "a space is not empty");
assert.deepEqual(dropBlank([]), [], "nothing to drop");
assert.deepEqual(dropBlank(["", ""]), [], "everything is empty");
assert.deepEqual(dropBlank(["  "]), ["  "], "spaces alone survive");
assert.deepEqual(dropBlank(["x"]), ["x"], "nothing needs dropping");
console.log("ok");
