import assert from "node:assert/strict";
import { foldSchemaEdits } from "./solution.ts";

assert.deepEqual(foldSchemaEdits(["one", "two"], []), ["one", "two"], "no edits changes nothing");
assert.deepEqual(
  foldSchemaEdits(["one", "two"], [{ op: "add", field: "three" }]),
  ["one", "two", "three"],
  "an add hangs on the end",
);
assert.deepEqual(
  foldSchemaEdits(["one", "two", "three"], [{ op: "drop", field: "two" }]),
  ["one", "three"],
  "a drop closes the gap behind it",
);
assert.deepEqual(
  foldSchemaEdits(["one", "two"], [{ op: "rename", field: "one", into: "first" }]),
  ["first", "two"],
  "a rename holds its place",
);
assert.deepEqual(
  foldSchemaEdits(["one", "two"], [
    { op: "drop", field: "two" },
    { op: "add", field: "two" },
  ]),
  ["one", "two"],
  "a heading freed by a drop may be added again",
);
assert.deepEqual(
  foldSchemaEdits(["one", "two"], [
    { op: "drop", field: "one" },
    { op: "rename", field: "two", into: "one" },
  ]),
  ["one"],
  "a rename may take over a freed heading",
);
assert.deepEqual(
  foldSchemaEdits(["one"], [{ op: "drop", field: "one" }]),
  [],
  "the header may run empty",
);

const rejects = (fields, edits) => {
  try {
    foldSchemaEdits(fields, edits);
  } catch {
    return true;
  }
  return false;
};

assert.ok(
  rejects(["one"], [{ op: "add", field: "two" }, { op: "add", field: "two" }]),
  "a heading brought in by an add may not be added twice",
);
assert.ok(
  rejects(["one"], [
    { op: "add", field: "two" },
    { op: "rename", field: "one", into: "two" },
  ]),
  "a rename may not take over a heading an add brought in",
);
assert.ok(rejects(["one", "two"], [{ op: "add", field: "one" }]), "add on a live heading is refused");
assert.ok(rejects(["one", "two"], [{ op: "rename", field: "one", into: "two" }]), "rename onto a live heading is refused");
assert.ok(rejects(["one"], [{ op: "drop", field: "gone" }]), "drop of an absent heading is refused");
assert.ok(rejects(["one"], [{ op: "shuffle", field: "one" }]), "an unknown op is refused");
assert.ok(rejects(["one"], [{ op: "rename", field: "one", into: "" }]), "an empty into is refused");
assert.ok(rejects(["one", "one"], []), "a repeat among the headings handed in is refused");
assert.ok(rejects([], []), "an empty header is refused");
assert.ok(rejects(["one"], [42]), "an edit that is not a mapping is refused");
console.log("ok");
