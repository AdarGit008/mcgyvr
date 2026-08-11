import assert from "node:assert/strict";
import { waveCount } from "./solution.ts";

assert.equal(waveCount([1, 3, 2]), 1, "up then down is one change");
assert.equal(waveCount([1, 2, 3]), 0, "a steady rise never changes");
assert.equal(waveCount([1, 3, 2, 4]), 2, "two changes");
assert.equal(waveCount([]), 0, "no readings at all");
assert.equal(waveCount([5, 5, 5]), 0, "level ground changes nothing");
assert.equal(waveCount([1, 3, 3, 2]), 1, "a level step does not break it");
console.log("ok");
