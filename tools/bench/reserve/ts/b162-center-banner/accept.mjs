import assert from "node:assert/strict";
import { centerBanner } from "./solution.ts";

assert.equal(centerBanner("OPEN", 10, " "), "   OPEN   ", "even spare cells split in half");
assert.equal(centerBanner("OPEN", 11, "."), "...OPEN....", "the odd spare cell goes right");
assert.equal(centerBanner("EXIT", 4, "*"), "EXIT", "an exact fit needs no fill");
assert.equal(centerBanner("", 3, "-"), "---", "an empty label yields fill alone");
assert.equal(centerBanner("x", 2, "_"), "x_", "a single spare cell goes right");
assert.equal(centerBanner("no vacancy", 12, " "), " no vacancy ", "inner spaces belong to the label");
assert.throws(() => centerBanner(7, 5, " "), Error, "a non-string label is rejected");
assert.throws(() => centerBanner("a\nb", 9, " "), Error, "a label holding a newline is rejected");
assert.throws(() => centerBanner("hi", 0, " "), Error, "a zero width is rejected");
assert.throws(() => centerBanner("overflow", 3, " "), Error, "a label wider than the board is rejected");
assert.throws(() => centerBanner("hi", 6, "--"), Error, "a two-character fill is rejected");
console.log("ok");
