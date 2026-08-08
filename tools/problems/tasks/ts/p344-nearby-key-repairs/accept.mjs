import assert from "node:assert/strict";
import { nearbyKeyRepairs } from "./solution.ts";

const board = { h: "gyjnb", o: "ipkl", n: "bhjm", e: "wrsd" };

assert.deepEqual(
  nearbyKeyRepairs("hone", ["bone", "hole", "home", "hose", "hire"], board),
  ["home", "bone"],
  "later place first, and only table neighbours qualify",
);
assert.deepEqual(
  nearbyKeyRepairs("wat", ["eat", "sat", "cat", "wit"], {
    w: "qeas",
    a: "qsz",
    t: "ryfg",
  }),
  ["eat", "sat"],
  "same place follows the table order",
);
assert.deepEqual(
  nearbyKeyRepairs("sat", ["wat", "eat", "xat", "zat", "dat"], {
    s: "awdxz",
    a: "qsz",
    t: "ryfg",
  }),
  ["wat", "dat", "xat"],
  "at most three answers",
);
assert.deepEqual(
  nearbyKeyRepairs("cat", ["cat", "bat"], { c: "xdfv" }),
  ["cat"],
  "a word the dictionary knows is answered alone",
);
assert.deepEqual(
  nearbyKeyRepairs("bat", ["cat", "bad"], { b: "vghn" }),
  [],
  "keys absent from the table yield nothing",
);
assert.deepEqual(
  nearbyKeyRepairs("q", ["w", "a"], { q: "wa" }),
  ["w", "a"],
  "a one-key word",
);
assert.deepEqual(nearbyKeyRepairs("hone", [], board), [], "an empty dictionary");
assert.throws(() => nearbyKeyRepairs("", ["a"], board), Error, "empty typed word");
assert.throws(() => nearbyKeyRepairs("Cat", ["cat"], board), Error, "uppercase typed");
assert.throws(() => nearbyKeyRepairs(9, ["cat"], board), Error, "typed not a string");
assert.throws(() => nearbyKeyRepairs("cat", "cat", board), Error, "dictionary not a list");
assert.throws(() => nearbyKeyRepairs("cat", ["Cat"], board), Error, "dictionary word cased");
assert.throws(() => nearbyKeyRepairs("cat", ["cot"], "xdfv"), Error, "table not a mapping");
assert.throws(
  () => nearbyKeyRepairs("cat", ["cot"], { ab: "xd" }),
  Error,
  "a two-letter table key",
);
assert.throws(
  () => nearbyKeyRepairs("cat", ["cot"], { c: "X" }),
  Error,
  "a table entry not lowercase",
);
assert.throws(
  () => nearbyKeyRepairs("cat", ["cot"], { c: "xc" }),
  Error,
  "a key neighbouring itself",
);
assert.throws(
  () => nearbyKeyRepairs("cat", ["cot"], { c: "xx" }),
  Error,
  "a repeated neighbour",
);
console.log("ok");
