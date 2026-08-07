import assert from "node:assert/strict";
import { sectionNumbers } from "./solution.ts";

assert.deepEqual(sectionNumbers("A", 2), ["1 A"], "one line gets 1");
assert.deepEqual(
  sectionNumbers("A\nB\nC", 2),
  ["1 A", "2 B", "3 C"],
  "flat lines count up"
);
assert.deepEqual(
  sectionNumbers("A\n  B\n    C", 2),
  ["1 A", "1.1 B", "1.1.1 C"],
  "a straight descent"
);
assert.deepEqual(
  sectionNumbers("A\n  B\n  C\nD\n  E", 2),
  ["1 A", "1.1 B", "1.2 C", "2 D", "2.1 E"],
  "counters restart under a new parent"
);
assert.deepEqual(
  sectionNumbers("A\n  B\n    C\nD\n  E\n    F", 2),
  ["1 A", "1.1 B", "1.1.1 C", "2 D", "2.1 E", "2.1.1 F"],
  "restart holds two levels down"
);
assert.deepEqual(
  sectionNumbers("A\n    B\n    C\nD\n    E", 4),
  ["1 A", "1.1 B", "1.2 C", "2 D", "2.1 E"],
  "a four-space unit behaves the same"
);
assert.throws(() => sectionNumbers("A", 0), Error, "zero unit");
assert.throws(() => sectionNumbers("A", 2.5), Error, "fractional unit");
assert.throws(() => sectionNumbers("A\n   B", 2), Error, "off-unit indentation");
assert.throws(() => sectionNumbers("A\n    B", 2), Error, "two-step jump");
assert.throws(() => sectionNumbers("  A", 2), Error, "opening line off margin");
console.log("ok");
