import assert from "node:assert/strict";
import { badgeText } from "./solution.ts";

assert.equal(badgeText("gate 4", {}), "gate 4", "a slotless pattern passes through");
assert.equal(badgeText("hi <who>", { who: "Ada" }), "hi Ada", "a slot takes its field value");
assert.equal(badgeText("<a>-<a>", { a: "x" }), "x-x", "the same field feeds two slots");
assert.equal(badgeText("<a><b>", { a: "to", b: "go" }), "togo", "adjacent slots join their values");
assert.equal(badgeText("<a>!", { a: "" }), "!", "an empty field value is legal");
assert.throws(() => badgeText(42, {}), Error, "a non-string pattern is rejected");
assert.throws(() => badgeText("a>b", {}), Error, "a closing bracket outside any slot is rejected");
assert.throws(() => badgeText("row <name", { name: "x" }), Error, "an unclosed opening bracket is rejected");
assert.throws(() => badgeText("<>", {}), Error, "an empty slot name is rejected");
assert.throws(() => badgeText("<Big>", { Big: "x" }), Error, "a slot name outside lowercase letters is rejected");
assert.throws(() => badgeText("<who> here", {}), Error, "a slot name the mapping lacks is rejected");
console.log("ok");
