import assert from "node:assert/strict";
import { orderRelation } from "./solution.ts";

const chain = [["a", "b"], ["b", "c"], ["c", "d"]];
assert.equal(orderRelation(chain, "a", "c"), "before", "transitive before");
assert.equal(orderRelation(chain, "d", "b"), "after", "transitive after");
assert.equal(orderRelation(chain, "a", "b"), "before", "direct edge");
const fork = [["a", "b"], ["a", "c"]];
assert.equal(orderRelation(fork, "b", "c"), "unordered", "siblings are unordered");
const loop = [["p", "q"], ["q", "r"], ["r", "p"]];
assert.equal(orderRelation(loop, "p", "r"), "both", "cycle reaches both ways");
const islands = [["a", "b"], ["c", "d"]];
assert.equal(orderRelation(islands, "a", "d"), "unordered", "disconnected items");
assert.equal(orderRelation([["m", "n"], ["n", "m"]], "m", "n"), "both", "two-cycle");
assert.throws(() => orderRelation(chain, "b", "b"), Error, "equal query items rejected");
assert.throws(() => orderRelation(chain, "a", "zz"), Error, "unknown item rejected");
console.log("ok");
