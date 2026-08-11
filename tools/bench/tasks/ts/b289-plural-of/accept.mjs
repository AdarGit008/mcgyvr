import assert from "node:assert/strict";
import { pluralOf } from "./solution.ts";

assert.equal(pluralOf("bus"), "buses", "an s takes es");
assert.equal(pluralOf("box"), "boxes", "an x takes es");
assert.equal(pluralOf("match"), "matches", "a ch takes es");
assert.equal(pluralOf("dish"), "dishes", "an sh takes es");
assert.equal(pluralOf("city"), "cities", "a consonant then y gives ies");
assert.equal(pluralOf("day"), "days", "a vowel then y just takes s");
assert.equal(pluralOf("cat"), "cats", "everything else takes s");
console.log("ok");
