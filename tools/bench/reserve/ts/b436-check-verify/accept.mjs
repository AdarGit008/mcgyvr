import assert from "node:assert/strict";
import { checkVerify } from "./solution.ts";

assert.equal(checkVerify("1234"), true, "the digits reach a multiple of ten");
assert.equal(checkVerify("1235"), false, "one digit out");
assert.equal(checkVerify("0"), true, "a nought checks out");
assert.equal(checkVerify("5"), false, "a lone five does not");
assert.equal(checkVerify("55"), true, "two fives make ten");
assert.equal(checkVerify("9991"), false, "twenty-eight is not a multiple of ten");
console.log("ok");
