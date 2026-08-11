import assert from "node:assert/strict";
import { voteLead } from "./solution.ts";

assert.equal(voteLead(["a", "b", "a"]), "a", "the clear winner");
assert.equal(voteLead(["b", "a"]), "a", "a tie goes alphabetically");
assert.equal(voteLead(["z"]), "z", "a single ballot decides it");
assert.equal(voteLead(["c", "c", "d", "d", "a"]), "c", "a tie at the top");
assert.equal(voteLead(["x", "x", "y", "y", "y"]), "y", "the later name still wins");
assert.throws(() => voteLead([]), Error, "no ballots is rejected");
console.log("ok");
