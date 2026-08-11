import assert from "node:assert/strict";
import { codeCase } from "./solution.ts";

assert.equal(codeCase("  ab-12 "), "AB-12", "trimmed and raised");
assert.equal(codeCase("xy9"), "XY9", "letters raised, digits alone");
assert.equal(codeCase("a b"), "A B", "an inner space survives");
assert.equal(codeCase("ALREADY"), "ALREADY", "already upper");
assert.throws(() => codeCase(""), Error, "an empty code is rejected");
assert.throws(() => codeCase("   "), Error, "spaces alone are rejected");
console.log("ok");
