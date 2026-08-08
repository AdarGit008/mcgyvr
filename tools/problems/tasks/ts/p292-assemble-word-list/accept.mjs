import assert from "node:assert/strict";
import { assembleWordList } from "./solution.ts";

assert.deepEqual(assembleWordList([]), [], "an empty source assembles to no words");
assert.deepEqual(
  assembleWordList(["; nothing but a remark", "   ", "spot:"]),
  [],
  "remarks, blank lines and a marker take no word",
);
assert.deepEqual(assembleWordList(["HALT"]), [16384], "HALT is a bare mnemonic");
assert.deepEqual(
  assembleWordList(["SET r0, 0", "SET r7, 255"]),
  [4096, 6143],
  "the register rides the 256 place and the immediate the ones",
);
assert.deepEqual(
  assembleWordList(["ADD r3,r5"]),
  [8965],
  "commas need no surrounding space",
);
assert.deepEqual(
  assembleWordList([
    "; wind down",
    "  SET r1, 3",
    "loop:",
    "  ADD r1, r2",
    "  JZ r1, done",
    "  JZ r0, loop",
    "done:",
    "  HALT",
  ]),
  [4355, 8450, 12545, 12541, 16384],
  "markers resolve both forward and backward",
);
assert.deepEqual(
  assembleWordList(["JZ r0, end", "end:"]),
  [12288],
  "a marker on the very next word is distance zero",
);
assert.deepEqual(
  assembleWordList(["here:", "JZ r3, here"]),
  [13311],
  "a jump onto itself is distance minus one",
);

const reach = ["far:"];
for (let n = 0; n < 127; n++) {
  reach.push("HALT");
}
reach.push("JZ r0, far");
assert.equal(
  assembleWordList(reach)[127],
  12288 + 128,
  "minus 128 is the furthest backward distance that still fits",
);

const overreach = ["far:"];
for (let n = 0; n < 128; n++) {
  overreach.push("HALT");
}
overreach.push("JZ r0, far");
assert.throws(
  () => assembleWordList(overreach),
  Error,
  "one word further back is out of range",
);

assert.throws(() => assembleWordList("SET r0, 1"), Error, "a string is not a list");
assert.throws(() => assembleWordList([7]), Error, "a line must be a string");
assert.throws(() => assembleWordList(["MOVE r1, r2"]), Error, "MOVE is no mnemonic");
assert.throws(() => assembleWordList(["HALT r1"]), Error, "HALT takes no operand");
assert.throws(() => assembleWordList(["SET r1"]), Error, "SET takes two operands");
assert.throws(() => assembleWordList(["SET r8, 1"]), Error, "there is no r8");
assert.throws(() => assembleWordList(["SET r1, 256"]), Error, "256 will not fit");
assert.throws(() => assembleWordList(["ADD r1, 4"]), Error, "ADD wants a register");
assert.throws(() => assembleWordList(["JZ r1, gone"]), Error, "no line plants gone");
assert.throws(
  () => assembleWordList(["twice:", "HALT", "twice:", "HALT"]),
  Error,
  "a marker may be planted only once",
);
assert.throws(() => assembleWordList(["set r1, 2"]), Error, "mnemonics are capitals");
console.log("ok");
