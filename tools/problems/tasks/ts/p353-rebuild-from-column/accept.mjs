import assert from "node:assert/strict";
import { rebuildFromLastColumn } from "./solution.ts";

assert.equal(
  rebuildFromLastColumn("nnbaaa", 3),
  "banana",
  "the stated banana column",
);
assert.equal(
  rebuildFromLastColumn("pssmipissii", 4),
  "mississippi",
  "a column thick with repeats",
);
assert.equal(
  rebuildFromLastColumn("rdarcaaaabb", 2),
  "abracadabra",
  "five a letters must keep their pairing",
);
assert.equal(rebuildFromLastColumn("vllee", 2), "level", "a short repeat");
assert.equal(rebuildFromLastColumn("eeffoc", 0), "coffee", "home at seat zero");
assert.equal(rebuildFromLastColumn("a", 0), "a", "a lone letter");
assert.equal(rebuildFromLastColumn("dabc", 0), "abcd", "all letters different");
assert.equal(rebuildFromLastColumn("mottoa", 4), "tomato", "home near the end");
assert.throws(
  () => rebuildFromLastColumn(9, 0),
  Error,
  "a column that is not a string is thrown out",
);
assert.throws(
  () => rebuildFromLastColumn("", 0),
  Error,
  "an empty column is thrown out",
);
assert.throws(
  () => rebuildFromLastColumn("ba7a", 1),
  Error,
  "a column outside a to z is thrown out",
);
assert.throws(
  () => rebuildFromLastColumn("abc", "1"),
  Error,
  "a home that is not a whole number is thrown out",
);
assert.throws(
  () => rebuildFromLastColumn("abc", 3),
  Error,
  "a home past the column is thrown out",
);
assert.throws(
  () => rebuildFromLastColumn("abc", -1),
  Error,
  "a home below zero is thrown out",
);
console.log("ok");
