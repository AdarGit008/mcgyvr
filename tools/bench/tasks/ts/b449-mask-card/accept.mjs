import assert from "node:assert/strict";
import { lastFour, maskCard } from "./solution.ts";

assert.equal(lastFour("123456"), "3456", "the last four");
assert.equal(lastFour("12"), "12", "a short number is all of it");
assert.equal(maskCard("123456"), "**3456", "two characters hidden");
assert.equal(maskCard("1234"), "1234", "nothing to hide");
assert.equal(maskCard(""), "", "an empty number");
assert.equal(maskCard("123456789"), "*****6789", "a longer number");
console.log("ok");
