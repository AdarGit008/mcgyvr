import assert from "node:assert/strict";
import { formatFixed, fillReport } from "./solution.ts";

assert.equal(formatFixed(3.14159, 2), "3.14", "plain two-decimal rendering");
assert.equal(formatFixed(2.5, 0), "3", "a positive half rounds away from zero");
assert.equal(formatFixed(-2.5, 0), "-3", "a negative half rounds away from zero");
assert.equal(formatFixed(-0.004, 2), "0.00", "a vanishing negative drops its sign");
assert.equal(formatFixed(1.999, 2), "2.00", "rounding carries into the whole part");
assert.equal(formatFixed(7, 0), "7", "zero decimals means no dot");
assert.equal(formatFixed(0.05, 1), "0.1", "a small value keeps its leading zero");
assert.equal(formatFixed(-7.25, 2), "-7.25", "a plain negative keeps its sign");
assert.throws(() => formatFixed(Infinity, 2), Error, "non-finite value is rejected");
assert.throws(() => formatFixed("9", 2), Error, "non-number value is rejected");
assert.throws(() => formatFixed(1.5, 7), Error, "decimals above six is rejected");
assert.throws(() => formatFixed(1.5, 0.5), Error, "fractional decimals is rejected");

assert.equal(fillReport("qty [n:4:0] units", { n: 42 }), "qty   42 units", "a slot pads on the left");
assert.equal(fillReport("[big:2:0]", { big: 12345 }), "12345", "a wide value is never truncated");
assert.equal(fillReport("[price:7:2]", { price: 3.5 }), "   3.50", "decimals flow through the slot");
assert.equal(fillReport("ok] [n:1:0]", { n: 1 }), "ok] 1", "a lone closing bracket is literal");
assert.throws(() => fillReport("[n:2:0", { n: 1 }), Error, "an unclosed slot is rejected");
assert.throws(() => fillReport("[ghost:2:0]", {}), Error, "a missing value is rejected");
assert.throws(() => fillReport("[n:x:0]", { n: 1 }), Error, "a malformed width is rejected");
assert.throws(() => fillReport("[n:2]", { n: 1 }), Error, "a two-part slot is rejected");
console.log("ok");
