import assert from "node:assert/strict";
import { shiftNoteLine } from "./solution.ts";

assert.deepEqual(
  shiftNoteLine(["C4", "E4", "G4"], 2, "sharp"),
  ["D4", "F#4", "A4"],
  "a whole tone up under the sharp table",
);
assert.deepEqual(
  shiftNoteLine(["C4", "E4", "G4"], 2, "flat"),
  ["D4", "Gb4", "A4"],
  "the same shift spelled the other way",
);
assert.deepEqual(
  shiftNoteLine(["B3"], 1, "sharp"),
  ["C4"],
  "a step past B climbs into the next octave",
);
assert.deepEqual(
  shiftNoteLine(["C4"], -1, "flat"),
  ["B3"],
  "a step below C falls into the octave beneath",
);
assert.deepEqual(
  shiftNoteLine(["F#3"], 3, "flat"),
  ["A3"],
  "a raised note reads its sign before the shift",
);
assert.deepEqual(
  shiftNoteLine(["Eb5"], -2, "flat"),
  ["Db5"],
  "a lowered note shifted downwards",
);
assert.deepEqual(
  shiftNoteLine(["Cb4"], 0, "sharp"),
  ["B3"],
  "a lowered C already sits in the octave below",
);
assert.deepEqual(
  shiftNoteLine(["B#4"], 0, "flat"),
  ["C5"],
  "a raised B already sits in the octave above",
);
assert.deepEqual(
  shiftNoteLine(["D4"], 0, "sharp"),
  ["D4"],
  "a shift of nothing still respells nothing",
);
assert.deepEqual(
  shiftNoteLine(["C4"], 12, "sharp"),
  ["C5"],
  "twelve half tones is one whole octave",
);
assert.deepEqual(
  shiftNoteLine(["A0", "C1"], -1, "sharp"),
  ["G#0", "B0"],
  "the lowest octave is reachable from above",
);
assert.deepEqual(shiftNoteLine([], 5, "flat"), [], "no notes shift to no notes");

assert.throws(
  () => shiftNoteLine("C4", 1, "sharp"),
  Error,
  "notes given as a string is rejected",
);
assert.throws(
  () => shiftNoteLine(["H4"], 1, "sharp"),
  Error,
  "a letter past G is rejected",
);
assert.throws(
  () => shiftNoteLine(["C"], 1, "sharp"),
  Error,
  "a note without an octave is rejected",
);
assert.throws(
  () => shiftNoteLine(["C##4"], 1, "sharp"),
  Error,
  "two signs at once are rejected",
);
assert.throws(
  () => shiftNoteLine(["c4"], 1, "sharp"),
  Error,
  "a small letter is rejected",
);
assert.throws(
  () => shiftNoteLine(["C4"], 1.5, "sharp"),
  Error,
  "a fractional shift is rejected",
);
assert.throws(
  () => shiftNoteLine(["C4"], 1, "wide"),
  Error,
  "a spelling outside the two words is rejected",
);
assert.throws(
  () => shiftNoteLine(["C0"], -1, "sharp"),
  Error,
  "falling below octave zero is rejected",
);
assert.throws(
  () => shiftNoteLine(["B9"], 1, "sharp"),
  Error,
  "climbing past octave nine is rejected",
);
console.log("ok");
