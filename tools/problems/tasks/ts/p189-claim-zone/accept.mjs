import assert from "node:assert/strict";
import { claimZone } from "./solution.ts";

const nest = ["0.0.0/0 world", "5.0.0/1 wing", "5.9.0/2 aisle", "5.9.15/3 slot"];

assert.equal(claimZone([], "1.2.3"), "", "no claims covers nothing");
assert.equal(claimZone(["0.0.0/0 world"], "5.9.15"), "world", "depth zero covers all");
assert.equal(claimZone(nest, "5.9.15"), "slot", "the deepest stencil wins");
assert.equal(
  claimZone([...nest].reverse(), "5.9.15"),
  "slot",
  "arrival order does not matter",
);
assert.equal(claimZone(nest, "5.9.14"), "aisle", "one number off drops a depth");
assert.equal(claimZone(nest, "5.10.0"), "wing", "two numbers off drops two depths");
assert.equal(claimZone(nest, "6.0.0"), "world", "only the widest stencil is left");
assert.equal(claimZone(nest.slice(1), "6.0.0"), "", "nothing covers it at all");
assert.equal(claimZone(["12.0.0/1 far"], "12.15.15"), "far", "two-digit numbers");
assert.equal(claimZone(["0.0.0/3 origin"], "0.0.0"), "origin", "the origin post");

assert.throws(
  () => claimZone(["1.0.0/1 a", "1.0.0/1 b"], "1.2.3"),
  Error,
  "a repeated stencil is rejected",
);
assert.throws(() => claimZone(["1.2.3/4 a"], "1.2.3"), Error, "depth four is rejected");
assert.throws(
  () => claimZone(["1.2.3/1 a"], "1.2.3"),
  Error,
  "a live number after the fixed ones is rejected",
);
assert.throws(() => claimZone(["1.2/2 a"], "1.2.3"), Error, "two numbers are rejected");
assert.throws(() => claimZone(["1.2.16/3 a"], "1.2.3"), Error, "sixteen is rejected");
assert.throws(() => claimZone(["01.2.3/3 a"], "1.2.3"), Error, "a padded number is rejected");
assert.throws(() => claimZone(["1.0.0/1"], "1.2.3"), Error, "a nameless claim is rejected");
assert.throws(() => claimZone(["1.0.0/1 "], "1.2.3"), Error, "an empty name is rejected");
assert.throws(() => claimZone(["1.0.0/1 a b"], "1.2.3"), Error, "a spaced name is rejected");
assert.throws(() => claimZone(["1.0.0-1 a"], "1.2.3"), Error, "a slashless stencil is rejected");
assert.throws(() => claimZone(nest, "1.2"), Error, "a short where is rejected");
assert.throws(() => claimZone("0.0.0/0 world", "1.2.3"), Error, "a bare string is rejected");
assert.throws(() => claimZone([5], "1.2.3"), Error, "a non-string claim is rejected");
console.log("ok");
