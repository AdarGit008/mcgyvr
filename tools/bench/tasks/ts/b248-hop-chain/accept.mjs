import assert from "node:assert/strict";
import { hopChain } from "./solution.ts";

assert.equal(hopChain([["a", "b"], ["b", "c"]]), true, "two hops meet");
assert.equal(hopChain([["a", "b"], ["c", "d"]]), false, "two hops do not meet");
assert.equal(hopChain([["a", "b"]]), true, "a single hop is unbroken");
assert.equal(hopChain([]), true, "no hops at all");
assert.equal(
  hopChain([["a", "b"], ["b", "c"], ["c", "d"]]),
  true,
  "three hops in a row",
);
assert.equal(
  hopChain([["a", "b"], ["b", "c"], ["x", "d"]]),
  false,
  "the last hop breaks the chain",
);
console.log("ok");
