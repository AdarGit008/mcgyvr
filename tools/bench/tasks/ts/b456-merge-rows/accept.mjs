import assert from "node:assert/strict";
import { rowKeys, mergeRows } from "./solution.ts";

assert.deepEqual(rowKeys({ a: "1", b: "2" }), ["a", "b"], "the names it holds");
assert.deepEqual(rowKeys({}), [], "an empty row holds none");
assert.deepEqual(mergeRows({ a: "1" }, { a: "9" }), { a: "9" }, "the row above wins");
assert.deepEqual(
  mergeRows({ a: "1" }, { b: "2" }),
  { a: "1", b: "2" },
  "no name is shared",
);
assert.deepEqual(mergeRows({}, {}), {}, "two empty rows");

const source = { a: "1" };
mergeRows(source, { a: "9" });
assert.deepEqual(source, { a: "1" }, "the row below is untouched");
console.log("ok");
