import assert from "node:assert/strict";
import { compileRules, bestAction } from "./solution.ts";

assert.deepEqual(
  compileRules([["invoice-????", "review"], ["*", "hold"]]),
  [
    { pattern: "invoice-????", action: "review", literals: 8 },
    { pattern: "*", action: "hold", literals: 0 },
  ],
  "compiled rules carry their literal counts",
);
assert.throws(() => compileRules([["", "x"]]), Error, "empty pattern");
assert.throws(() => compileRules([["a*b*", "x"]]), Error, "second star");
assert.throws(() => compileRules([["ab", ""]]), Error, "empty action");
assert.throws(() => compileRules([["ab", "x"], ["ab", "y"]]), Error, "repeated pattern");
const billing = compileRules([
  ["*", "any"],
  ["invoice-??", "short"],
  ["invoice-2026", "exact"],
]);
assert.equal(bestAction(billing, "invoice-2026"), "exact", "most literals win over rule order");
assert.equal(bestAction(billing, "invoice-77"), "short", "a ? run fits its exact length");
const cache = compileRules([["cache", "hit"]]);
assert.equal(bestAction(cache, "cachex"), null, "a starless pattern refuses longer text");
assert.equal(bestAction(cache, "cache"), "hit", "a starless pattern fits its own length");
const logs = compileRules([["log*", "keep"]]);
assert.equal(bestAction(logs, "log"), "keep", "a star may span nothing");
const sweeps = compileRules([["*.tmp", "sweep"]]);
assert.equal(bestAction(sweeps, "notes.tmp"), "sweep", "a star-led tail anchors at the end");
assert.equal(bestAction(sweeps, "notes.tmp.bak"), null, "text past the tail refuses");
const loops = compileRules([["ab*ba", "loop"]]);
assert.equal(bestAction(loops, "abba"), "loop", "head and tail may touch");
assert.equal(bestAction(loops, "aba"), null, "text shorter than head plus tail refuses");
const tie = compileRules([["a?c", "first"], ["?bc", "second"]]);
assert.equal(bestAction(tie, "abc"), "first", "equal literals go to the earlier rule");
assert.equal(bestAction(compileRules([]), "anything"), null, "no rules, no action");
assert.throws(() => bestAction(cache, 42), Error, "non-string candidate");
console.log("ok");
