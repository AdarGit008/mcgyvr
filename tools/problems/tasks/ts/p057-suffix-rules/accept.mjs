import assert from "node:assert/strict";
import { applyInflections } from "./solution.ts";

assert.equal(
  applyInflections("city", [["y", "ies"]]),
  "cities",
  "a matched tail is swapped for the replacement",
);
assert.equal(
  applyInflections("yummy", [["y", "ies"]]),
  "yummies",
  "a suffix also present early in the word must still rewrite the tail",
);
assert.equal(
  applyInflections("wayside", [["way", "ways"]]),
  "wayside",
  "a rule must not fire when only the middle of the word contains it",
);
assert.equal(
  applyInflections("bus", [
    ["s", "ses"],
    ["us", "i"],
  ]),
  "buses",
  "the first matching rule wins over later ones",
);
assert.equal(
  applyInflections("ox", [["s", "es"]]),
  "ox",
  "a word no rule matches is unchanged",
);
assert.equal(
  applyInflections("ox", [["ox", "oxen"]]),
  "oxen",
  "a suffix may cover the whole word",
);
assert.equal(
  applyInflections("analysis", [["sis", "ses"]]),
  "analyses",
  "multi-character tails rewrite cleanly",
);
assert.equal(applyInflections("cat", []), "cat", "an empty table changes nothing");
assert.throws(
  () => applyInflections("cat", [["", "s"]]),
  Error,
  "an empty suffix is rejected",
);
console.log("ok");
