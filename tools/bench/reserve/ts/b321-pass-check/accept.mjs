import assert from "node:assert/strict";
import { passCheck } from "./solution.ts";

assert.equal(passCheck("abcd1234"), true, "long enough with both");
assert.equal(passCheck("abcdefgh"), false, "no digit");
assert.equal(passCheck("12345678"), false, "no letter");
assert.equal(passCheck("ab12"), false, "too short");
assert.equal(passCheck(""), false, "an empty passphrase");
assert.equal(passCheck("Passw0rdd"), true, "capitals count as letters");
console.log("ok");
