import assert from "node:assert/strict";
import { findMotifSites } from "./solution.ts";

assert.deepEqual(findMotifSites("AACGTT", "ACG"), [1], "a plain motif sits once");
assert.deepEqual(findMotifSites("AAAA", "AA"), [0, 1, 2], "sittings may overlap");
assert.deepEqual(
  findMotifSites("ACGTACGT", "N"),
  [0, 1, 2, 3, 4, 5, 6, 7],
  "N sits on every letter of the strand",
);
assert.deepEqual(findMotifSites("ACGT", "RY"), [0, 2], "R and Y each cover two letters");
assert.deepEqual(findMotifSites("GGCC", "S"), [0, 1, 2, 3], "S covers C and G");
assert.deepEqual(findMotifSites("AT", "W"), [0, 1], "W covers A and T");
assert.deepEqual(findMotifSites("ACGTG", "KM"), [], "a motif that fits nowhere sits nowhere");
assert.deepEqual(findMotifSites("TAGC", "KM"), [0, 2], "K and M read in that order");
assert.deepEqual(findMotifSites("ACGTACGT", "ACGT"), [0, 4], "a long plain motif sits twice");
assert.deepEqual(findMotifSites("AC", "ACG"), [], "a motif longer than the strand sits nowhere");
assert.deepEqual(findMotifSites("", "A"), [], "an empty strand holds nothing");
assert.deepEqual(
  findMotifSites("GATTACA", "NNN"),
  [0, 1, 2, 3, 4],
  "a run of N sits at every full-length window",
);
assert.deepEqual(
  findMotifSites("CAGGTAAGT", "GGTRAGT"),
  [2],
  "a mixed motif pins one site in a longer strand",
);

assert.throws(() => findMotifSites("ACGT", ""), Error, "an empty motif is rejected");
assert.throws(() => findMotifSites("ACGT", "ACX"), Error, "an unnamed motif symbol is rejected");
assert.throws(() => findMotifSites("ACGT", "acg"), Error, "a lowercase motif is rejected");
assert.throws(() => findMotifSites("ACGN", "AC"), Error, "a degenerate symbol in the strand is rejected");
assert.throws(() => findMotifSites(5, "AC"), Error, "a non-string strand is rejected");
assert.throws(() => findMotifSites("ACGT", 5), Error, "a non-string motif is rejected");
console.log("ok");
