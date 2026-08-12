import assert from "node:assert/strict";
import { nestGet } from "./solution.ts";

assert.equal(nestGet({ a: { b: "deep" } }, ["a", "b"]), "deep", "two steps down");
assert.equal(nestGet({ a: "top" }, ["a"]), "top", "one step down");
assert.equal(nestGet({ a: "top" }, ["b"]), "", "the path leads nowhere");
assert.equal(nestGet({ a: "top" }, []), "", "an empty path finds nothing");
assert.equal(nestGet({ a: { b: "deep" } }, ["a"]), "", "a mapping is not text");
assert.equal(
  nestGet({ a: { b: { c: "far" } } }, ["a", "b", "c"]),
  "far",
  "three steps down",
);
console.log("ok");
