import assert from "node:assert/strict";
import { valueKeys } from "./solution.ts";

assert.deepEqual(valueKeys({ a: "x", b: "x" }), { x: 2 }, "two keys share a value");
assert.deepEqual(valueKeys({ a: "x" }), { x: 1 }, "one key, one value");
assert.deepEqual(valueKeys({}), {}, "an empty store");
assert.deepEqual(valueKeys({ a: "x", b: "y" }), { x: 1, y: 1 }, "two separate values");
assert.deepEqual(valueKeys({ a: "" }), { "": 1 }, "an empty value counts");
assert.deepEqual(
  valueKeys({ a: "x", b: "x", c: "y" }),
  { x: 2, y: 1 },
  "a mix of shared and lone",
);
console.log("ok");
