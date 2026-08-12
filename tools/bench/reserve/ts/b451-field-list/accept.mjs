import assert from "node:assert/strict";
import { fieldOr, fieldList } from "./solution.ts";

assert.equal(fieldOr({ a: "1" }, "a", "-"), "1", "the field is held");
assert.equal(fieldOr({}, "a", "-"), "-", "the stand-in is used");
assert.deepEqual(fieldList([{ a: "1" }, {}], "a", "-"), ["1", "-"], "one of each");
assert.deepEqual(fieldList([], "a", "-"), [], "no records at all");
assert.deepEqual(fieldList([{ b: "1" }], "a", "-"), ["-"], "the field is never held");
assert.equal(fieldOr({ a: "" }, "a", "-"), "", "an empty value is still a value");
console.log("ok");
