import assert from "node:assert/strict";
import { hueBand } from "./solution.ts";

assert.equal(hueBand(0), "red", "the circle starts red");
assert.equal(hueBand(59), "red", "just below the green edge");
assert.equal(hueBand(60), "green", "green begins at its edge");
assert.equal(hueBand(179), "green", "just below the blue edge");
assert.equal(hueBand(180), "blue", "blue begins at its edge");
assert.equal(hueBand(300), "red", "red returns at the far edge");
assert.equal(hueBand(400), "red", "a reading past the circle wraps");
assert.equal(hueBand(-30), "red", "a negative reading counts backwards");
console.log("ok");
