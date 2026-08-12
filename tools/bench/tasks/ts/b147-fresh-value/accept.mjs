import assert from "node:assert/strict";
import { freshValue } from "./solution.ts";

assert.equal(freshValue({ value: "a", stored: 5, ttl: 10 }, 5), "a", "a record is usable the tick it is stored");
assert.equal(freshValue({ value: "b", stored: 5, ttl: 10 }, 14), "b", "the last usable tick still yields the value");
assert.equal(freshValue({ value: "tok", stored: 0, ttl: 1 }, 0), "tok", "a one-tick record works at tick zero");
assert.equal(freshValue({ value: "", stored: 2, ttl: 3 }, 3), "", "an empty string is a value like any other");
assert.equal(freshValue({ value: "z", stored: 100, ttl: 50 }, 120), "z", "a mid-life record yields its value");
assert.throws(() => freshValue(42, 0), Error, "an entry that is not a record is rejected");
assert.throws(() => freshValue({ value: 7, stored: 0, ttl: 5 }, 0), Error, "a non-string value is rejected");
assert.throws(() => freshValue({ value: "a", stored: -1, ttl: 5 }, 0), Error, "a negative stored is rejected");
assert.throws(() => freshValue({ value: "a", stored: 0, ttl: 0 }, 0), Error, "a zero ttl is rejected");
assert.throws(() => freshValue({ value: "a", stored: 9, ttl: 5 }, 8), Error, "a now before stored is rejected");
assert.throws(() => freshValue({ value: "a", stored: 5, ttl: 10 }, 15), Error, "the record stops being usable at stored plus ttl");
console.log("ok");
