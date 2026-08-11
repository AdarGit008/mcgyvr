import assert from "node:assert/strict";
import { rollbackJournal } from "./solution.ts";

assert.deepEqual(rollbackJournal(["a", "b"], [], 0), ["a", "b"], "zero rollback copies");
const doc = ["z", "a", "m", "b"];
const journal = [["insert", 1, "m"], ["insert", 0, "z"]];
assert.deepEqual(
  rollbackJournal(doc, journal, 2),
  ["a", "b"],
  "entries unwind newest first across nearby indexes",
);
assert.deepEqual(doc, ["z", "a", "m", "b"], "the argument is left unmodified");
assert.deepEqual(
  rollbackJournal(doc, journal, 1),
  ["a", "m", "b"],
  "a partial rollback undoes only the newest entry",
);
assert.deepEqual(
  rollbackJournal(["a", "c"], [["delete", 1, "b"]], 1),
  ["a", "b", "c"],
  "a delete is undone by putting its line back",
);
assert.deepEqual(
  rollbackJournal(["a", "B"], [["replace", 1, "b", "B"]], 1),
  ["a", "b"],
  "a replace is undone by restoring its before text",
);
assert.deepEqual(
  rollbackJournal(["cap"], [["delete", 1, "tail"], ["replace", 0, "cup", "cap"]], 2),
  ["cup", "tail"],
  "mixed kinds unwind in reverse order",
);
assert.throws(
  () => rollbackJournal(["a", 1], [], 0),
  Error,
  "a non-string line is rejected",
);
assert.throws(() => rollbackJournal(["a"], "x", 0), Error, "a non-list journal is rejected");
assert.throws(
  () => rollbackJournal(["a"], [["insert", 0, "a"]], 2),
  Error,
  "a count past the journal is rejected",
);
assert.throws(
  () => rollbackJournal(["a"], [["insert", 0]], 1),
  Error,
  "an entry missing its fields is rejected",
);
assert.throws(
  () => rollbackJournal(["a"], [["insert", 5, "a"]], 1),
  Error,
  "an index outside the document is rejected",
);
assert.throws(
  () => rollbackJournal(["a"], [["insert", 0, "b"]], 1),
  Error,
  "an insert whose text misses its line is rejected",
);
assert.throws(
  () => rollbackJournal(["a"], [["replace", 0, "b", "c"]], 1),
  Error,
  "a replace whose after text misses its line is rejected",
);
console.log("ok");
