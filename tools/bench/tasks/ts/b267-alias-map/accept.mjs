import assert from "node:assert/strict";
import { aliasResolve, aliasNames } from "./solution.ts";

assert.equal(aliasResolve({ a: "b" }, "a"), "b", "one hop");
assert.equal(aliasResolve({ a: "b", b: "c" }, "a"), "b", "no second hop is taken");
assert.equal(aliasResolve({ a: "b" }, "z"), "z", "a name that stands for nothing");
assert.equal(aliasResolve({}, "x"), "x", "no aliases at all");
assert.deepEqual(aliasNames({ birch: "b", alder: "a" }), ["alder", "birch"], "sorted");
assert.deepEqual(aliasNames({}), [], "no names to list");
console.log("ok");
