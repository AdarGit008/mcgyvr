import assert from "node:assert/strict";
import { kernedRunWidth } from "./solution.ts";

const face = { A: 7, V: 7, W: 9, a: 5, i: 1, j: 0, ".": 3, " ": 4 };

assert.equal(kernedRunWidth("", face, [], 4), 0, "an empty run measures zero");
assert.equal(kernedRunWidth("A", face, [["AV", -3]], 3), 7, "one character takes no tracking");
assert.equal(kernedRunWidth("AA", face, [], 1), 15, "one couple takes one tracking");
assert.equal(
  kernedRunWidth("AVa", face, [["AV", -3], ["Va", -1], ["AV", -99]], 1),
  17,
  "both couples draw from the table and the lower AV row is dead weight",
);
assert.equal(
  kernedRunWidth("AV", face, [["AV", -3], ["AV", 5]], 0),
  11,
  "the higher row of a repeated couple is the one that counts",
);
assert.equal(
  kernedRunWidth("Va", face, [["AV", -3]], 0),
  12,
  "a table row for another couple grants nothing",
);
assert.equal(
  kernedRunWidth("A V", face, [], 2),
  22,
  "a space advances and carries tracking on both sides",
);
assert.equal(
  kernedRunWidth("AAA", face, [], -2),
  17,
  "tracking may pull the run in",
);
assert.equal(kernedRunWidth("jj", face, [], 0), 0, "a zero advance is allowed");
assert.equal(
  kernedRunWidth("WAV.", face, [["AV", -4], ["V.", -6]], 0),
  16,
  "four characters and two granted couples",
);

assert.throws(() => kernedRunWidth(5, face, [], 0), Error, "a run is a string");
assert.throws(() => kernedRunWidth("A", [], [], 0), Error, "widths is a mapping");
assert.throws(() => kernedRunWidth("Z", face, [], 0), Error, "Z has no width");
assert.throws(() => kernedRunWidth("A", { A: 1.5 }, [], 0), Error, "a width is whole");
assert.throws(() => kernedRunWidth("A", { A: -1 }, [], 0), Error, "a width is not negative");
assert.throws(() => kernedRunWidth("A", face, "none", 0), Error, "kerns is a list");
assert.throws(() => kernedRunWidth("AV", face, [["A", -1]], 0), Error, "a couple is two characters");
assert.throws(() => kernedRunWidth("AV", face, [["AV", 0.5]], 0), Error, "a kern is whole");
assert.throws(() => kernedRunWidth("AV", face, [], 1.5), Error, "tracking is whole");
assert.throws(
  () => kernedRunWidth("ii", { i: 1 }, [["ii", -5]], 0),
  Error,
  "a run may not measure below zero",
);
console.log("ok");
