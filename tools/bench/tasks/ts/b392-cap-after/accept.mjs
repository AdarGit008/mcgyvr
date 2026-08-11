import assert from "node:assert/strict";
import { capAfter } from "./solution.ts";

assert.equal(capAfter("hi. there"), "Hi. There", "both sentences are capitalised");
assert.equal(capAfter("hi"), "Hi", "one sentence with no full stop");
assert.equal(capAfter(""), "", "an empty passage");
assert.equal(capAfter("a. b. c"), "A. B. C", "three short sentences");
assert.equal(capAfter("  hi"), "  Hi", "leading spaces are not letters");
assert.equal(capAfter("HI. ho"), "HI. Ho", "other letters are left alone");
console.log("ok");
