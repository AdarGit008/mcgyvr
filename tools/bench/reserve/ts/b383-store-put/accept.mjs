import assert from "node:assert/strict";
import { putOne, putAll } from "./solution.ts";

assert.deepEqual(putOne({ a: "1" }, "b", "2"), { a: "1", b: "2" }, "a key is set");
assert.deepEqual(putOne({ a: "1" }, "a", "9"), { a: "9" }, "an existing key is replaced");
assert.deepEqual(
  putAll({}, [["a", "1"], ["b", "2"]]),
  { a: "1", b: "2" },
  "several keys at once",
);
assert.deepEqual(putAll({ a: "1" }, []), { a: "1" }, "nothing to set");

const source = { a: "1" };
putOne(source, "b", "2");
assert.deepEqual(source, { a: "1" }, "the caller's store is untouched");
assert.throws(() => putOne({}, "", "x"), Error, "an empty key is rejected");
console.log("ok");
