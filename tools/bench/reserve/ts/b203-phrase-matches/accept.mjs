import assert from "node:assert/strict";
import { phraseMatches } from "./solution.ts";

assert.equal(phraseMatches("raise the mast", ["raise", "the", "mast"]), true, "plain tokens match word for word");
assert.equal(phraseMatches("raise * mast", ["raise", "the", "second", "mast"]), true, "a star spans several words");
assert.equal(phraseMatches("raise * mast", ["raise", "mast"]), true, "a star also spans no words at all");
assert.equal(phraseMatches("raise ? mast", ["raise", "mast"]), false, "a question mark demands one word");
assert.equal(phraseMatches("* mast", ["mast", "hoist"]), false, "words left over after the tokens fail");
assert.equal(phraseMatches("raise|lower the ?", ["lower", "the", "gaff"]), true, "a barred token takes any of its pieces");
assert.equal(phraseMatches("raise|lower the ?", ["furl", "the", "gaff"]), false, "a word outside the pieces fails");
console.log("ok");
