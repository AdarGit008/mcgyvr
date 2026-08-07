import assert from "node:assert/strict";
import { applySchemaSteps } from "./solution.ts";

const base = [
  { name: "id", kind: "int" },
  { name: "label", kind: "text" },
];

assert.deepEqual(
  applySchemaSteps(base, []),
  [
    { name: "id", kind: "int" },
    { name: "label", kind: "text" },
  ],
  "an empty step list leaves the table as it was",
);

assert.deepEqual(
  applySchemaSteps(base, [{ op: "add", name: "seen_at", kind: "long" }]),
  [
    { name: "id", kind: "int" },
    { name: "label", kind: "text" },
    { name: "seen_at", kind: "long" },
  ],
  "an add lands at the end",
);

assert.deepEqual(base, [
  { name: "id", kind: "int" },
  { name: "label", kind: "text" },
], "the argument is left untouched");

assert.deepEqual(
  applySchemaSteps(
    [
      { name: "a1", kind: "int" },
      { name: "b2", kind: "int" },
      { name: "c3", kind: "long" },
    ],
    [{ op: "drop", name: "b2" }],
  ),
  [
    { name: "a1", kind: "int" },
    { name: "c3", kind: "long" },
  ],
  "a drop closes the gap behind it",
);

assert.deepEqual(
  applySchemaSteps(base, [{ op: "rename", name: "id", to: "row_key" }]),
  [
    { name: "row_key", kind: "int" },
    { name: "label", kind: "text" },
  ],
  "a rename keeps place and kind",
);

assert.deepEqual(
  applySchemaSteps(base, [{ op: "retype", name: "id", kind: "long" }]),
  [
    { name: "id", kind: "long" },
    { name: "label", kind: "text" },
  ],
  "int widens to long",
);

assert.deepEqual(
  applySchemaSteps(base, [
    { op: "drop", name: "label" },
    { op: "add", name: "label", kind: "long" },
    { op: "retype", name: "label", kind: "text" },
    { op: "rename", name: "id", to: "label2" },
  ]),
  [
    { name: "label2", kind: "int" },
    { name: "label", kind: "text" },
  ],
  "a freed name may be taken again later in the run",
);

assert.deepEqual(
  applySchemaSteps(base, [{ op: "retype", name: "id", kind: "text" }]),
  [
    { name: "id", kind: "text" },
    { name: "label", kind: "text" },
  ],
  "int may skip straight to text",
);

const rejects = (columns, steps) => {
  try {
    applySchemaSteps(columns, steps);
  } catch {
    return true;
  }
  return false;
};

assert.ok(rejects([], []), "an empty table is refused");
assert.ok(rejects(base, [{ op: "add", name: "id", kind: "int" }]), "add on a taken name is refused");
assert.ok(rejects(base, [{ op: "drop", name: "gone" }]), "drop of an absent column is refused");
assert.ok(
  rejects([{ name: "only", kind: "int" }], [{ op: "drop", name: "only" }]),
  "the last column may not be dropped",
);
assert.ok(rejects(base, [{ op: "rename", name: "id", to: "label" }]), "rename onto a taken name is refused");
assert.ok(rejects(base, [{ op: "rename", name: "id", to: "id" }]), "rename onto its own name is refused");
assert.ok(rejects(base, [{ op: "retype", name: "label", kind: "int" }]), "a narrowing retype is refused");
assert.ok(rejects(base, [{ op: "retype", name: "id", kind: "int" }]), "a retype to the held kind is refused");
assert.ok(rejects(base, [{ op: "widen", name: "id", kind: "text" }]), "an unknown op is refused");
assert.ok(rejects(base, [{ op: "add", name: "Bad", kind: "int" }]), "a name of the wrong shape is refused");
assert.ok(rejects(base, [{ op: "add", name: "ok_name", kind: "blob" }]), "an unknown kind is refused");
assert.ok(rejects([{ name: "x", kind: "int" }, { name: "x", kind: "text" }], []), "a repeated column name is refused");
assert.ok(rejects(base, [null]), "a step that is not a mapping is refused");
assert.ok(rejects("nope", []), "a table that is not a list is refused");
console.log("ok");
