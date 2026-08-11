import assert from "node:assert/strict";
import { sizeUnit, sizeText } from "./solution.ts";

assert.equal(sizeUnit(500), "B", "under a kilobyte");
assert.equal(sizeUnit(2000), "KB", "over a kilobyte");
assert.equal(sizeText(500), "500 B", "written in bytes");
assert.equal(sizeText(3000), "2 KB", "a kilobyte is 1024 bytes");
assert.equal(sizeText(1024), "1 KB", "exactly one kilobyte");
assert.equal(sizeText(0), "0 B", "nothing at all");
assert.throws(() => sizeText(-1), Error, "a negative count is rejected");
console.log("ok");
