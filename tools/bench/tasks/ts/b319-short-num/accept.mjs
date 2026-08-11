import assert from "node:assert/strict";
import { shortNum } from "./solution.ts";

assert.equal(shortNum(1200), "1.2k", "a thousand takes k");
assert.equal(shortNum(999), "999", "below a thousand is written out");
assert.equal(shortNum(1000), "1.0k", "exactly a thousand");
assert.equal(shortNum(1500000), "1.5m", "a million takes m");
assert.equal(shortNum(0), "0", "nothing is written out");
assert.equal(shortNum(1999), "1.9k", "the decimal rounds down");
console.log("ok");
