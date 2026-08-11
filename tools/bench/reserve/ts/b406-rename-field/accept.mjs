import assert from "node:assert/strict";
import { renameField } from "./solution.ts";

assert.deepEqual(renameField([{ a: 1 }], "a", "b"), [{ b: 1 }], "the old name goes");
assert.deepEqual(renameField([{ c: 1 }], "a", "b"), [{ c: 1 }], "no such field");
assert.deepEqual(renameField([], "a", "b"), [], "no records at all");
assert.deepEqual(
  renameField([{ a: 1, c: 2 }], "a", "b"),
  [{ b: 1, c: 2 }],
  "other fields are kept",
);
assert.deepEqual(
  renameField([{ a: 1 }, { a: 2 }], "a", "b"),
  [{ b: 1 }, { b: 2 }],
  "every record is renamed",
);

const source = [{ a: 1 }];
renameField(source, "a", "b");
assert.deepEqual(source, [{ a: 1 }], "the records given are untouched");
console.log("ok");
