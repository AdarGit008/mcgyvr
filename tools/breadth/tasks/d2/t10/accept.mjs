import assert from "node:assert/strict";
import { addDecimalStrings } from "./solution.ts";

assert.equal(addDecimalStrings("2", "3"), "5", "single digits");
assert.equal(addDecimalStrings("0", "0"), "0", "zero plus zero is exactly 0");
assert.equal(addDecimalStrings("99", "1"), "100", "carry ripples through");
assert.equal(addDecimalStrings("999999999", "1"), "1000000000", "long carry chain");
assert.equal(addDecimalStrings("1", "999"), "1000", "shorter first operand");
assert.equal(addDecimalStrings("007", "08"), "15", "leading zeros in inputs");
assert.equal(addDecimalStrings("000", "000"), "0", "all-zero inputs normalize to 0");
assert.equal(
  addDecimalStrings("9007199254740993", "9007199254740993"),
  "18014398509481986",
  "beyond Number precision"
);
assert.equal(
  addDecimalStrings("123456789012345678901234567890", "987654321098765432109876543210"),
  "1111111110111111111011111111100",
  "30-digit operands"
);
assert.equal(
  addDecimalStrings("1".repeat(100), "8".repeat(100)),
  "9".repeat(100),
  "100-digit operands, no carry"
);
assert.equal(
  addDecimalStrings("9".repeat(60), "1"),
  "1" + "0".repeat(60),
  "60-digit carry chain"
);

assert.throws(() => addDecimalStrings("", "1"), Error, "empty string throws");
assert.throws(() => addDecimalStrings("12", "3a"), Error, "non-digit character throws");
assert.throws(() => addDecimalStrings("-1", "2"), Error, "sign is invalid");
assert.throws(() => addDecimalStrings("1.5", "2"), Error, "decimal point is invalid");
assert.throws(() => addDecimalStrings(12, "3"), Error, "non-string throws");
assert.throws(() => addDecimalStrings("1 2", "3"), Error, "space is invalid");
