import assert from "node:assert/strict";
import { thawRow } from "./solution.ts";

assert.equal(thawRow("###", 0), "###", "zero steps returns the row unchanged");
assert.equal(thawRow("###", 1), ".#.", "both ends melt in one step");
assert.equal(thawRow("###", 2), "...", "the core goes on the second step");
assert.equal(thawRow("#####", 1), ".###.", "only the exposed ends melt");
assert.equal(thawRow("##.##", 1), ".....", "a water pocket melts both of its walls");
assert.equal(thawRow("...", 4), "...", "meltwater never refreezes");
assert.equal(thawRow("#", 1), ".", "a lone ice cell melts at once");
assert.throws(() => thawRow(42, 1), Error, "a non-string row is rejected");
assert.throws(() => thawRow("", 1), Error, "an empty row is rejected");
assert.throws(() => thawRow("#x#", 1), Error, "a stray character is rejected");
assert.throws(() => thawRow("##", 1.5), Error, "a fractional step count is rejected");
console.log("ok");
