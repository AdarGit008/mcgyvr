import assert from "node:assert/strict";
import { formatBits } from "./solution.ts";

assert.equal(formatBits(0, 4), "0000", "zero pads to the full width");
assert.equal(formatBits(5, 4), "0101", "a single nibble renders directly");
assert.equal(formatBits(300, 12), "0001 0010 1100", "wider values group in fours");
assert.equal(formatBits(255, 8), "1111 1111", "a saturated byte is all ones");
assert.equal(
  formatBits(1, 32),
  "0000 0000 0000 0000 0000 0000 0000 0001",
  "the widest allowed width still renders",
);
assert.throws(() => formatBits(16, 4), Error, "a value too wide for the width");
assert.throws(() => formatBits(5, 10), Error, "a width off the nibble grid");
assert.throws(() => formatBits(1, 36), Error, "a width beyond 32 bits");
assert.throws(() => formatBits(-3, 8), Error, "a negative value is rejected");
console.log("ok");
