import assert from "node:assert/strict";
import { nameTriadStack } from "./solution.ts";

assert.deepEqual(nameTriadStack([0, 4, 7]), { base: 0, name: "major" }, "the plainest shape");
assert.deepEqual(
  nameTriadStack([60, 64, 67, 72, 76]),
  { base: 0, name: "major" },
  "repeats and higher octaves fold away",
);
assert.deepEqual(
  nameTriadStack([-12, -8, -5]),
  { base: 0, name: "major" },
  "negative marks fold up into range",
);
assert.deepEqual(nameTriadStack([4, 7, 11]), { base: 4, name: "minor" }, "a base away from zero");
assert.deepEqual(
  nameTriadStack([7, 11, 2]),
  { base: 7, name: "major" },
  "the marks need not arrive in order",
);
assert.deepEqual(
  nameTriadStack([0, 4, 8]),
  { base: 0, name: "augmented" },
  "every class fits the same row so the smallest wins",
);
assert.deepEqual(nameTriadStack([0, 5, 7]), { base: 0, name: "quartal" }, "a quartal at zero");
assert.deepEqual(
  nameTriadStack([0, 2, 7]),
  { base: 7, name: "quartal" },
  "only one turn of this stack is in the table",
);
assert.deepEqual(nameTriadStack([0, 2, 6]), { base: 0, name: "narrow" }, "a narrow shape");
assert.deepEqual(nameTriadStack([0, 3, 6]), { base: 0, name: "diminished" }, "a diminished shape");
assert.deepEqual(
  nameTriadStack([0, 3, 6, 9]),
  { base: 0, name: "shrunk seventh" },
  "four classes all fitting one row",
);
assert.deepEqual(
  nameTriadStack([0, 4, 7, 11]),
  { base: 0, name: "major seventh" },
  "a four-class row",
);
assert.deepEqual(
  nameTriadStack([0, 4, 7, 10]),
  { base: 0, name: "dominant seventh" },
  "another four-class row",
);
assert.deepEqual(
  nameTriadStack([0, 3, 7, 10]),
  { base: 0, name: "minor seventh" },
  "a third four-class row",
);
assert.deepEqual(
  nameTriadStack([0, 1, 2]),
  { base: -1, name: "unknown" },
  "no turn of this stack is in the table",
);
assert.throws(() => nameTriadStack("047"), Error, "a non-list argument is rejected");
assert.throws(() => nameTriadStack([]), Error, "an empty list is rejected");
assert.throws(() => nameTriadStack([0, 1.5, 4]), Error, "a fractional mark is rejected");
assert.throws(() => nameTriadStack([0, "4", 7]), Error, "a non-number mark is rejected");
assert.throws(() => nameTriadStack([0, 12, 24]), Error, "one class after folding is rejected");
assert.throws(() => nameTriadStack([0, 4]), Error, "two classes are rejected");
console.log("ok");
