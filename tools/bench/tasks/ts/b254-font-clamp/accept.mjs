import assert from "node:assert/strict";
import { fontClamp } from "./solution.ts";

assert.equal(fontClamp(5, 8, 20), 8, "below the range comes up");
assert.equal(fontClamp(30, 8, 20), 20, "above the range comes down");
assert.equal(fontClamp(12, 8, 20), 12, "inside the range is untouched");
assert.equal(fontClamp(8, 8, 20), 8, "sitting on the lower edge");
assert.equal(fontClamp(20, 8, 20), 20, "sitting on the upper edge");
assert.throws(() => fontClamp(5, 20, 8), Error, "an inverted range is rejected");
console.log("ok");
