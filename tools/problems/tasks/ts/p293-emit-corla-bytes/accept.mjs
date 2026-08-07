import assert from "node:assert/strict";
import { emitCorlaBytes } from "./solution.ts";

assert.deepEqual(emitCorlaBytes([]), [], "an empty listing settles no bytes");
assert.deepEqual(
  emitCorlaBytes(["# only a note", "", "  ", ".idle"]),
  [],
  "notes, blank rows and a spot occupy nothing",
);
assert.deepEqual(
  emitCorlaBytes(["NOP", "STOP", "LOAD 0", "LOAD 255"]),
  [0, 64, 16, 0, 16, 255],
  "the one and two byte keywords lay down in order",
);
assert.deepEqual(
  emitCorlaBytes([
    "# a small routine",
    ".top",
    "LOAD 7",
    "CALL .helper",
    "GOTO .done",
    ".helper",
    "NOP",
    "STOP",
    ".done",
    "STOP",
  ]),
  [16, 7, 48, 0, 8, 32, 0, 10, 0, 64, 64],
  "spots further down the listing carry their true byte address",
);
assert.deepEqual(
  emitCorlaBytes([".begin", "NOP", "GOTO .begin"]),
  [0, 32, 0, 0],
  "a spot already passed still resolves",
);

const wide = ["GOTO .far"];
for (let n = 0; n < 300; n++) {
  wide.push("NOP");
}
wide.push(".far", "STOP");
const wideBytes = emitCorlaBytes(wide);
assert.deepEqual(
  [wideBytes[0], wideBytes[1], wideBytes[2]],
  [32, 1, 47],
  "an address past 255 splits into a high and a low byte",
);
assert.equal(wideBytes.length, 304, "three bytes, three hundred, then one");

assert.throws(() => emitCorlaBytes("NOP"), Error, "text is not a list of rows");
assert.throws(() => emitCorlaBytes([12]), Error, "a row must be text");
assert.throws(() => emitCorlaBytes(["JUMP .x", ".x"]), Error, "JUMP is no keyword");
assert.throws(() => emitCorlaBytes(["NOP 1"]), Error, "NOP carries no argument");
assert.throws(() => emitCorlaBytes(["LOAD"]), Error, "LOAD wants its v");
assert.throws(() => emitCorlaBytes(["LOAD 256"]), Error, "256 is past the ceiling");
assert.throws(() => emitCorlaBytes(["GOTO .gone"]), Error, "no row names gone");
assert.throws(
  () => emitCorlaBytes([".done", "NOP", "GOTO done"]),
  Error,
  "an argument spot keeps its full stop",
);
assert.throws(
  () => emitCorlaBytes([".Twice", "NOP"]),
  Error,
  "a spot is spelled in lowercase",
);
assert.throws(
  () => emitCorlaBytes([".same", "NOP", ".same", "NOP"]),
  Error,
  "a spot may be named only once",
);
console.log("ok");
