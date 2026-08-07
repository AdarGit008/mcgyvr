import assert from "node:assert/strict";
import { openSweepCascade } from "./solution.ts";

assert.deepEqual(
  openSweepCascade(["*---", "----", "----", "---*"], [0, 3]),
  { view: ["?100", "1100", "0011", "001?"], opened: 14, struck: false },
  "a zero square opens the whole of the bare ground",
);
assert.deepEqual(
  openSweepCascade(["*---", "----", "----", "---*"], [3, 3]),
  { view: ["????", "????", "????", "???!"], opened: 0, struck: true },
  "starting on a bomb is struck",
);
assert.deepEqual(
  openSweepCascade(["-"], [0, 0]),
  { view: ["0"], opened: 1, struck: false },
  "one bare square",
);
assert.deepEqual(
  openSweepCascade(["*"], [0, 0]),
  { view: ["!"], opened: 0, struck: true },
  "one square holding a bomb",
);
assert.deepEqual(
  openSweepCascade(["-----", "*****", "-----"], [0, 0]),
  { view: ["2????", "?????", "?????"], opened: 1, struck: false },
  "a square above zero carries the spread no further",
);
assert.deepEqual(
  openSweepCascade(["-----", "-*-*-", "-----", "-----"], [3, 4]),
  { view: ["?????", "?????", "11211", "00000"], opened: 10, struck: false },
  "the spread halts on the ring of digits it opened",
);
assert.deepEqual(
  openSweepCascade(["------", "--*---", "------", "---*--"], [0, 0]),
  { view: ["01????", "01????", "012???", "001???"], opened: 10, struck: false },
  "the spread rounds a bomb without opening it",
);
assert.deepEqual(
  openSweepCascade(["-*-", "---", "-*-"], [1, 1]),
  { view: ["???", "?2?", "???"], opened: 1, struck: false },
  "a lone opened square between two bombs",
);
assert.throws(
  () => openSweepCascade("--", [0, 0]),
  Error,
  "a board that is not a list is thrown out",
);
assert.throws(
  () => openSweepCascade([], [0, 0]),
  Error,
  "a board with no lines is thrown out",
);
assert.throws(
  () => openSweepCascade([["-"]], [0, 0]),
  Error,
  "a line that is not a string is thrown out",
);
assert.throws(
  () => openSweepCascade(["--", ""], [0, 0]),
  Error,
  "an empty line is thrown out",
);
assert.throws(
  () => openSweepCascade(["--", "---"], [0, 0]),
  Error,
  "lines of unequal length are thrown out",
);
assert.throws(
  () => openSweepCascade(["-x-"], [0, 0]),
  Error,
  "a symbol outside star and dash is thrown out",
);
assert.throws(
  () => openSweepCascade(["---"], [0]),
  Error,
  "an origin that is not a pair is thrown out",
);
assert.throws(
  () => openSweepCascade(["---"], [0, "1"]),
  Error,
  "an origin that is not whole is thrown out",
);
assert.throws(
  () => openSweepCascade(["---"], [0, 3]),
  Error,
  "an origin off the board is thrown out",
);
assert.throws(
  () => openSweepCascade(["---"], [-1, 0]),
  Error,
  "an origin above the board is thrown out",
);
console.log("ok");
