import assert from "node:assert/strict";
import { cloudCode } from "./solution.ts";

assert.equal(cloudCode({ CL: "clear" }, "CL"), "clear", "a plain lookup");
assert.equal(cloudCode({ CL: "clear" }, "cl"), "clear", "lower case still matches");
assert.equal(cloudCode({ RN: "rain" }, "Rn"), "rain", "mixed case still matches");
assert.equal(cloudCode({ CL: "clear" }, "RN"), "unknown", "a code not in the table");
assert.equal(cloudCode({}, "CL"), "unknown", "an empty table");
assert.equal(cloudCode({ CL: "" }, "CL"), "", "an empty description is not unknown");
console.log("ok");
