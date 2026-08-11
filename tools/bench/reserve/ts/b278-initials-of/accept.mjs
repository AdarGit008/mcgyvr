import assert from "node:assert/strict";
import { initialsOf } from "./solution.ts";

assert.equal(initialsOf("ada lovelace"), "A.L.", "two words, two initials");
assert.equal(initialsOf("Grace  Brewster   Hopper"), "G.B.H.", "wide gaps are one break");
assert.equal(initialsOf("prince"), "P.", "one word still closes with a dot");
assert.equal(initialsOf(""), "", "no name, no initials");
assert.equal(initialsOf("   "), "", "spaces alone hold no words");
assert.equal(initialsOf("  jo  ann  "), "J.A.", "the ends are ignored");
console.log("ok");
