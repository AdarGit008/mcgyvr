import assert from "node:assert/strict";
import { digitCount } from "./solution.ts";

assert.equal(digitCount(0), 1, "nothing takes one digit");
assert.equal(digitCount(5), 1, "a single digit");
assert.equal(digitCount(42), 2, "two digits");
assert.equal(digitCount(1000), 4, "four digits");
assert.equal(digitCount(-37), 2, "the minus sign is not counted");
assert.equal(digitCount(999999), 6, "six digits");
console.log("ok");
