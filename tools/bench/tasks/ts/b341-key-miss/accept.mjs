import assert from "node:assert/strict";
import { lookUp } from "./solution.ts";

assert.equal(lookUp({ a: "1" }, "a", "x"), "1", "the stored value");
assert.equal(lookUp({}, "a", "x"), "x", "an absent key takes the fallback");
assert.equal(lookUp({ a: "" }, "a", "x"), "", "an empty value is still a value");
assert.equal(lookUp({ a: "1" }, "b", "x"), "x", "a different key is absent");
assert.equal(lookUp({ a: "0" }, "a", "x"), "0", "a zero is a value too");
assert.equal(lookUp({ b: "y" }, "b", ""), "y", "the fallback may be empty");
console.log("ok");
