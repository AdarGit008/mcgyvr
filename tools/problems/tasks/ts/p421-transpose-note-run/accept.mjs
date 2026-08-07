import assert from "node:assert/strict";
import { transposeNoteRun } from "./solution.ts";

assert.deepEqual(
  transposeNoteRun(["C4", "E4", "G4"], 2, 4, []),
  ["E4", "G#4", "B4"],
  "three letters up and four half tones up keeps the chord's shape",
);
assert.deepEqual(
  transposeNoteRun(["Eb4"], 2, 4, []),
  ["G4"],
  "a lowered note may land with no signs at all",
);
assert.deepEqual(
  transposeNoteRun(["Bb3"], 4, 7, []),
  ["F4"],
  "a walk past the end of the ladder carries the octave up",
);
assert.deepEqual(
  transposeNoteRun(["B4"], 1, 2, []),
  ["C#5"],
  "the letter wraps and the sign is worked out afterwards",
);
assert.deepEqual(
  transposeNoteRun(["C4"], -1, -2, []),
  ["Bb3"],
  "a backwards walk carries the octave down",
);
assert.deepEqual(
  transposeNoteRun(["G#4"], 2, 4, []),
  ["B#4"],
  "a raised B is written rather than borrowing the letter above",
);
assert.deepEqual(
  transposeNoteRun(["B#4"], 1, 2, []),
  ["C##5"],
  "two hashes are written when one will not reach",
);
assert.deepEqual(
  transposeNoteRun(["Cb4"], 1, 2, []),
  ["Db4"],
  "a lowered C keeps its written octave when it moves",
);
assert.deepEqual(
  transposeNoteRun(["F#3"], 0, 0, []),
  ["F#3"],
  "no rung and no size leaves a note exactly as it was",
);
assert.deepEqual(
  transposeNoteRun(["D4"], 7, 12, []),
  ["D5"],
  "seven rungs and twelve half tones is a plain octave",
);
assert.deepEqual(
  transposeNoteRun(["F4"], 2, 3, ["F#"]),
  ["A4"],
  "a stamped letter sounds raised before it is moved",
);
assert.deepEqual(
  transposeNoteRun(["F4"], 2, 3, []),
  ["Ab4"],
  "the same move without the stamp lands a half tone lower",
);
assert.deepEqual(
  transposeNoteRun(["Fb4"], 2, 3, ["F#"]),
  ["Abb4"],
  "a note wearing its own sign pays the stamp no attention",
);
assert.deepEqual(
  transposeNoteRun(["B3", "E4"], 0, 0, ["Bb", "Eb"]),
  ["Bb3", "Eb4"],
  "standing still writes the key out in full",
);
assert.deepEqual(transposeNoteRun([], 3, 5, []), [], "no notes move to no notes");

assert.throws(
  () => transposeNoteRun("C4", 1, 2, []),
  Error,
  "notes given as a string is rejected",
);
assert.throws(
  () => transposeNoteRun(["H4"], 1, 2, []),
  Error,
  "a letter past G is rejected",
);
assert.throws(
  () => transposeNoteRun(["C###4"], 1, 2, []),
  Error,
  "three signs are rejected",
);
assert.throws(
  () => transposeNoteRun(["C#b4"], 1, 2, []),
  Error,
  "signs of two minds are rejected",
);
assert.throws(
  () => transposeNoteRun(["C4"], 1.5, 2, []),
  Error,
  "a fractional rung is rejected",
);
assert.throws(
  () => transposeNoteRun(["C4"], 1, "2", []),
  Error,
  "a size given as a string is rejected",
);
assert.throws(
  () => transposeNoteRun(["C4"], 1, 2, "F#"),
  Error,
  "a key given as a string is rejected",
);
assert.throws(
  () => transposeNoteRun(["C4"], 1, 2, ["F"]),
  Error,
  "a stamp without a sign is rejected",
);
assert.throws(
  () => transposeNoteRun(["C4"], 1, 2, ["F##"]),
  Error,
  "a stamp with two signs is rejected",
);
assert.throws(
  () => transposeNoteRun(["C4"], 1, 2, ["F#", "Fb"]),
  Error,
  "one letter stamped twice is rejected",
);
assert.throws(
  () => transposeNoteRun(["B##4"], 1, 2, []),
  Error,
  "a move needing three signs is rejected",
);
assert.throws(
  () => transposeNoteRun(["C9"], 7, 12, []),
  Error,
  "climbing past octave nine is rejected",
);
assert.throws(
  () => transposeNoteRun(["C0"], -1, -2, []),
  Error,
  "falling below octave zero is rejected",
);
console.log("ok");
