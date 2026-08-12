import assert from "node:assert/strict";
import { ordinalOf } from "./solution.ts";

assert.equal(ordinalOf(1), "1st", "one takes st");
assert.equal(ordinalOf(2), "2nd", "two takes nd");
assert.equal(ordinalOf(3), "3rd", "three takes rd");
assert.equal(ordinalOf(4), "4th", "everything else takes th");
assert.equal(ordinalOf(11), "11th", "the teens are the exception");
assert.equal(ordinalOf(12), "12th", "and so is twelve");
assert.equal(ordinalOf(13), "13th", "and thirteen");
assert.equal(ordinalOf(21), "21st", "past the teens the rule returns");
console.log("ok");
