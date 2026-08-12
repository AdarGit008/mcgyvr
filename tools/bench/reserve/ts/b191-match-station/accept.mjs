import assert from "node:assert/strict";
import { matchStation } from "./solution.ts";

const names = ["Harbor", "Harbor Annex", "Harborview", "North Harbor", "Depot"];

assert.equal(matchStation(names, "harbor"), "Harbor", "an exact name beats the names that merely begin with it");
assert.equal(matchStation(names, "HarborV"), "Harborview", "letter case is ignored on both sides");
assert.equal(matchStation(names, "harb"), "Harbor", "the shortest name beginning with the fragment wins");
assert.equal(matchStation(names, "annex"), "Harbor Annex", "a name holding the fragment inside serves when none begins with it");
assert.equal(matchStation(["Quarry Yard", "Quarry Halt"], "quarry"), "Quarry Halt", "names of equal length break the tie alphabetically");
assert.equal(matchStation(names, "wharf"), null, "a fragment no name holds resolves to nothing");
assert.throws(() => matchStation(names, ""), Error, "an empty fragment is rejected");
console.log("ok");
