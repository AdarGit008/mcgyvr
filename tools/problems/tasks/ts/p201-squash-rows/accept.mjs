import assert from "node:assert/strict";
import { squashRows } from "./solution.ts";

const row = (label, mark, next) => ({ label, mark, next });

assert.deepEqual(
  squashRows({
    signals: ["s"],
    head: "A",
    rows: [row("A", "red", ["A"]), row("B", "blue", ["B"])],
  }),
  {
    entry: 0,
    rows: [
      { at: 0, mark: "red", next: [0] },
      { at: 1, mark: "blue", next: [1] },
    ],
  },
  "rows with unlike marks stay apart"
);

assert.deepEqual(
  squashRows({
    signals: ["s"],
    head: "A",
    rows: [row("A", "red", ["A"]), row("B", "red", ["B"])],
  }),
  { entry: 0, rows: [{ at: 0, mark: "red", next: [0] }] },
  "two self-leading rows under one mark are twins"
);

assert.deepEqual(
  squashRows({
    signals: ["s"],
    head: "A",
    rows: [
      row("A", "x", ["B"]),
      row("B", "x", ["C"]),
      row("C", "y", ["C"]),
      row("D", "x", ["E"]),
      row("E", "x", ["F"]),
      row("F", "y", ["F"]),
    ],
  }),
  {
    entry: 0,
    rows: [
      { at: 0, mark: "x", next: [1] },
      { at: 1, mark: "x", next: [2] },
      { at: 2, mark: "y", next: [2] },
    ],
  },
  "twins may lead to different rows so long as those are twins in turn"
);

assert.deepEqual(
  squashRows({
    signals: ["s"],
    head: "A",
    rows: [row("A", "x", ["B"]), row("B", "x", ["C"]), row("C", "y", ["C"])],
  }),
  {
    entry: 0,
    rows: [
      { at: 0, mark: "x", next: [1] },
      { at: 1, mark: "x", next: [2] },
      { at: 2, mark: "y", next: [2] },
    ],
  },
  "a shared mark is not enough when the marks ahead diverge"
);

assert.deepEqual(
  squashRows({
    signals: ["p", "q"],
    head: "A",
    rows: [
      row("A", "go", ["B", "C"]),
      row("B", "stop", ["A", "A"]),
      row("C", "stop", ["A", "A"]),
    ],
  }),
  {
    entry: 0,
    rows: [
      { at: 0, mark: "go", next: [1, 1] },
      { at: 1, mark: "stop", next: [0, 0] },
    ],
  },
  "two signals, and both point at the one squashed group"
);

assert.deepEqual(
  squashRows({
    signals: ["s"],
    head: "B",
    rows: [row("A", "x", ["A"]), row("B", "y", ["B"])],
  }),
  {
    entry: 1,
    rows: [
      { at: 0, mark: "x", next: [0] },
      { at: 1, mark: "y", next: [1] },
    ],
  },
  "the entry follows the head wherever it landed"
);

assert.deepEqual(
  squashRows({
    signals: ["s"],
    head: "A",
    rows: [row("A", "x", ["A"]), row("Z", "y", ["Z"]), row("W", "y", ["W"])],
  }),
  {
    entry: 0,
    rows: [
      { at: 0, mark: "x", next: [0] },
      { at: 1, mark: "y", next: [1] },
    ],
  },
  "rows nothing leads to are squashed and kept all the same"
);

assert.deepEqual(
  squashRows({
    signals: ["s"],
    head: "P",
    rows: [row("P", "x", ["P"]), row("Q", "y", ["Q"]), row("R", "x", ["R"])],
  }),
  {
    entry: 0,
    rows: [
      { at: 0, mark: "x", next: [0] },
      { at: 1, mark: "y", next: [1] },
    ],
  },
  "a group takes the number of its earliest member"
);

const sound = {
  signals: ["s"],
  head: "A",
  rows: [row("A", "x", ["A"])],
};
const bent = (patch) => squashRows({ ...sound, ...patch });

assert.throws(() => bent({ signals: [] }), Error, "no signals at all is rejected");
assert.throws(
  () => bent({ signals: ["s", "s"] }),
  Error,
  "a signal listed twice is rejected"
);
assert.throws(() => bent({ rows: [] }), Error, "a chart with no rows is rejected");
assert.throws(
  () => bent({ rows: [row("A", "x", ["A"]), row("A", "y", ["A"])] }),
  Error,
  "two rows sharing a label are rejected"
);
assert.throws(
  () => bent({ rows: [row("A", "", ["A"])] }),
  Error,
  "an empty mark is rejected"
);
assert.throws(
  () => bent({ rows: [row("A", "x", ["A", "A"])] }),
  Error,
  "a next list longer than the signals is rejected"
);
assert.throws(
  () => bent({ rows: [row("A", "x", ["nowhere"])] }),
  Error,
  "a next entry naming no row is rejected"
);
assert.throws(() => bent({ head: "Q" }), Error, "a head naming no row is rejected");

console.log("ok");
