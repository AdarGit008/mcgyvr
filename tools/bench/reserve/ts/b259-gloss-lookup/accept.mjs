import assert from "node:assert/strict";
import { glossFind, glossTerms } from "./solution.ts";

assert.equal(glossFind({ Ash: "a tree" }, "ash"), "a tree", "lower case finds it");
assert.equal(glossFind({ Ash: "a tree" }, "ASH"), "a tree", "upper case finds it");
assert.equal(glossFind({ Ash: "a tree" }, "oak"), null, "an absent term");
assert.equal(glossFind({}, "any"), null, "an empty glossary");
assert.deepEqual(glossTerms({ birch: "", alder: "" }), ["alder", "birch"], "sorted");
assert.deepEqual(glossTerms({}), [], "no terms to list");
console.log("ok");
