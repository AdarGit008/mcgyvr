import assert from "node:assert/strict";
import { parseByteSize } from "./solution.ts";

assert.equal(parseByteSize("512B"), 512, "plain bytes");
assert.equal(parseByteSize("4KiB"), 4096, "kibibytes");
assert.equal(parseByteSize("3MiB"), 3145728, "mebibytes");
assert.equal(parseByteSize("2GiB"), 2147483648, "gibibytes");
assert.equal(parseByteSize("0B"), 0, "a zero count is zero bytes");
assert.throws(() => parseByteSize(42), Error, "non-string is rejected");
assert.throws(() => parseByteSize(""), Error, "empty string is rejected");
assert.throws(() => parseByteSize("KiB"), Error, "missing count is rejected");
assert.throws(() => parseByteSize("12"), Error, "missing unit is rejected");
assert.throws(() => parseByteSize("12KB"), Error, "decimal spelling is unknown");
assert.throws(() => parseByteSize("12 KiB"), Error, "stray character is rejected");
console.log("ok");
