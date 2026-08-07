import assert from "node:assert/strict";
import { leafPaths } from "./solution.ts";

assert.deepEqual(
  leafPaths([["root", ""], ["a", "root"], ["b", "root"], ["c", "a"]]),
  ["root/a/c", "root/b"],
  "two leaves, one nested",
);
assert.deepEqual(leafPaths([["only", ""]]), ["only"], "a lone root is a leaf");
assert.deepEqual(
  leafPaths([["r", ""], ["m", "r"], ["n", "m"]]),
  ["r/m/n"],
  "a chain yields one path",
);
assert.deepEqual(
  leafPaths([["c", "a"], ["root", ""], ["a", "root"], ["b", "root"]]),
  ["root/a/c", "root/b"],
  "row order does not matter",
);
assert.deepEqual(
  leafPaths([["r", ""], ["z", "r"], ["a", "r"]]),
  ["r/a", "r/z"],
  "paths come back sorted",
);
assert.throws(
  () => leafPaths([["r", ""], ["a", "r"], ["a", "r"]]),
  Error,
  "duplicated id rejected",
);
assert.throws(
  () => leafPaths([["r", ""], ["a", "ghost"]]),
  Error,
  "unknown parent rejected",
);
assert.throws(
  () => leafPaths([["r", ""], ["s", ""]]),
  Error,
  "two roots rejected",
);
assert.throws(
  () => leafPaths([["a", "b"], ["b", "a"]]),
  Error,
  "no root rejected",
);
assert.throws(() => leafPaths([]), Error, "empty input rejected");
assert.throws(
  () => leafPaths([["r", ""], ["a", "b"], ["b", "a"]]),
  Error,
  "rows off the root rejected",
);
console.log("ok");
