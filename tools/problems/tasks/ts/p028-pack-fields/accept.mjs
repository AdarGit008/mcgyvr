import assert from "node:assert/strict";
import { packFields } from "./solution.ts";

assert.equal(packFields([4, 4], [10, 3]), 163, "two nibbles, high then low");
assert.equal(packFields([4, 4], [3, 10]), 58, "swapped values change the result");
assert.equal(packFields([1, 3, 4], [1, 5, 9]), 217, "mixed widths");
assert.equal(packFields([8], [255]), 255, "single full byte");
assert.equal(packFields([4, 4], [0, 15]), 15, "leading zero field keeps its width");
assert.equal(packFields([3, 3], [0, 0]), 0, "all-zero fields pack to zero");
assert.equal(packFields([15, 15], [32767, 32767]), 1073741823, "full 30 bits");
assert.equal(packFields([2, 2, 2], [1, 2, 3]), 27, "three two-bit fields");
assert.throws(() => packFields([4, 4], [1]), Error, "unequal lengths are rejected");
assert.throws(() => packFields([], []), Error, "empty lists are rejected");
assert.throws(() => packFields([0, 4], [0, 1]), Error, "zero width is rejected");
assert.throws(() => packFields([16, 15], [0, 0]), Error, "31 combined bits are rejected");
assert.throws(() => packFields([4], [16]), Error, "oversized value is rejected");
assert.throws(() => packFields([4], [-1]), Error, "negative value is rejected");
assert.throws(() => packFields([4], [1.5]), Error, "fractional value is rejected");
console.log("ok");
