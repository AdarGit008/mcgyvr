import assert from "node:assert/strict";
import { oxfordJoin } from "./solution.ts";

assert.equal(oxfordJoin(["a", "b", "c"]), "a, b and c", "three names");
assert.equal(oxfordJoin(["a", "b"]), "a and b", "two names take no comma");
assert.equal(oxfordJoin(["a"]), "a", "one name stands alone");
assert.equal(oxfordJoin([]), "", "no names at all");
assert.equal(oxfordJoin(["a", "b", "c", "d"]), "a, b, c and d", "four names");
assert.equal(oxfordJoin(["x", "y"]), "x and y", "another pair");
console.log("ok");
