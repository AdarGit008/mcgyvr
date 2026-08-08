import assert from "node:assert/strict";
import { unspoolText } from "./solution.ts";

assert.equal(unspoolText("abc"), "abc", "text with no pointer is itself");
assert.equal(unspoolText(""), "", "the empty spool produces nothing");
assert.equal(unspoolText("ab<2,2>"), "abab", "a pointer that does not overlap");
assert.equal(unspoolText("ab<1,4>"), "abbbbb", "a haul larger than its reach");
assert.equal(
  unspoolText("xyz<3,3><6,6>"),
  "xyzxyzxyzxyz",
  "a pointer reading what an earlier pointer wrote",
);
assert.equal(unspoolText("ab<<c"), "ab<c", "a doubled sign is one literal sign");
assert.equal(unspoolText("a>b"), "a>b", "a lone greater-than sign is literal");
assert.equal(unspoolText("<<"), "<", "a spool that is only the escape");
assert.equal(unspoolText("ha<2,10>"), "hahahahahaha", "a long overlapping haul");
assert.equal(unspoolText("abcd<4,2>ef"), "abcdabef", "text resumes after a pointer");
assert.equal(unspoolText("ab<2,2>>"), "abab>", "a closer followed by a literal");
assert.equal(unspoolText("ab<2,1>"), "aba", "a haul of one");

assert.throws(() => unspoolText("<1,2>"), Error, "a pointer with nothing behind it");
assert.throws(() => unspoolText("ab<3,1>"), Error, "a reach past the start");
assert.throws(() => unspoolText("ab<2>"), Error, "a missing comma is rejected");
assert.throws(() => unspoolText("ab<2,2"), Error, "a missing closer is rejected");
assert.throws(() => unspoolText("ab<0,2>"), Error, "a zero reach is rejected");
assert.throws(() => unspoolText("ab<2,0>"), Error, "a zero haul is rejected");
assert.throws(() => unspoolText("ab<02,2>"), Error, "a padded reach is rejected");
assert.throws(() => unspoolText("ab<x,2>"), Error, "a non-numeric field is rejected");
assert.throws(() => unspoolText("ab<"), Error, "a dangling sign is rejected");
assert.throws(() => unspoolText(3), Error, "a non-string spool is rejected");
console.log("ok");
