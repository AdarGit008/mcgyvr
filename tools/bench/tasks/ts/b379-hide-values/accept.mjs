import assert from "node:assert/strict";
import { hideValues } from "./solution.ts";

assert.deepEqual(hideValues({ a: "xy" }), { a: "**" }, "one star per character");
assert.deepEqual(hideValues({}), {}, "nothing to hide");
assert.deepEqual(hideValues({ ab: "" }), { ab: "" }, "an empty value hides to nothing");
assert.deepEqual(
  hideValues({ a: "x", b: "yz" }),
  { a: "*", b: "**" },
  "each value keeps its own length",
);
assert.deepEqual(hideValues({ k: "abc" }), { k: "***" }, "a longer value");
assert.deepEqual(hideValues({ longkey: "x" }), { longkey: "*" }, "the key is untouched");
console.log("ok");
