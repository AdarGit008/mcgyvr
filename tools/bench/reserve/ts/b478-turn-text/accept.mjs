import assert from "node:assert/strict";
import { turnText } from "./solution.ts";

assert.equal(turnText("abcd", "cdab"), true, "two characters moved to the back");
assert.equal(turnText("abcd", "dabc"), true, "one character moved to the back");
assert.equal(turnText("abcd", "abdc"), false, "the order inside is broken");
assert.equal(turnText("abc", "abcd"), false, "texts of unlike length");
assert.equal(turnText("aab", "aba"), true, "a repeated character still turns");
assert.equal(turnText("", ""), true, "two texts holding nothing");
console.log("ok");
