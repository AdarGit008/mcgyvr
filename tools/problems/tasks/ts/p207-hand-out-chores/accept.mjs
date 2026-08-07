import assert from "node:assert/strict";
import { handOutChores } from "./solution.ts";

assert.deepEqual(
  handOutChores(["mop", "dust", "sweep"], ["Ann", "Bo", "Cy"]),
  { Ann: ["mop", "dust"], Bo: ["sweep"], Cy: [] },
  "the step is the chore's own length",
);
assert.deepEqual(
  handOutChores([], ["Ann", "Bo"]),
  { Ann: [], Bo: [] },
  "an empty board still names the whole crew",
);
assert.deepEqual(
  handOutChores(["a", "bb", "ccc"], ["Xu", "Yi"]),
  { Xu: ["a"], Yi: ["bb", "ccc"] },
  "a step of two lands back on the same person",
);
assert.deepEqual(
  handOutChores(["a", "b"], ["Solo"]),
  { Solo: ["a", "b"] },
  "a crew of one takes everything",
);
assert.deepEqual(
  handOutChores(["longer", "x"], ["A", "B", "C", "D"]),
  { A: ["longer"], B: [], C: ["x"], D: [] },
  "the marker wraps around the ring",
);
assert.deepEqual(
  handOutChores(["ab", "cd", "ef"], ["P", "Q"]),
  { P: ["ab", "cd", "ef"], Q: [] },
  "an even step can starve half the ring",
);
assert.throws(() => handOutChores("mop", ["Ann"]), Error, "a board that is not a list is rejected");
assert.throws(() => handOutChores([""], ["Ann"]), Error, "an empty chore is rejected");
assert.throws(() => handOutChores([9], ["Ann"]), Error, "a non-string chore is rejected");
assert.throws(() => handOutChores(["mop", "mop"], ["Ann"]), Error, "a chore listed twice is rejected");
assert.throws(() => handOutChores(["mop"], "Ann"), Error, "a crew that is not a list is rejected");
assert.throws(() => handOutChores(["mop"], []), Error, "an empty crew is rejected");
assert.throws(() => handOutChores(["mop"], [""]), Error, "an empty crew name is rejected");
assert.throws(() => handOutChores(["mop"], [7]), Error, "a non-string crew name is rejected");
assert.throws(() => handOutChores(["mop"], ["Ann", "Ann"]), Error, "two crew members sharing a name is rejected");
console.log("ok");
