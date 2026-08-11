import assert from "node:assert/strict";
import { ordinalStamp } from "./solution.ts";

assert.equal(ordinalStamp(2000, 1), "2000-01-01 Saturday", "the anchor day stamps itself");
assert.equal(ordinalStamp(2024, 60), "2024-02-29 Thursday", "day 60 of a long year is the extra day");
assert.equal(ordinalStamp(2023, 60), "2023-03-01 Wednesday", "day 60 of a short year has crossed into March");
assert.equal(ordinalStamp(2023, 365), "2023-12-31 Sunday", "the last day of a short year");
assert.equal(ordinalStamp(2024, 366), "2024-12-31 Tuesday", "the last day of a long year");
assert.equal(ordinalStamp(2000, 366), "2000-12-31 Sunday", "a year divisible by 400 is long");
assert.throws(() => ordinalStamp(2023, 366), Error, "day 366 of a short year is rejected");
assert.throws(() => ordinalStamp(1999, 1), Error, "a year before the anchor is rejected");
console.log("ok");
