import assert from "node:assert/strict";
import { auditBranchReplies } from "./solution.ts";

const items = [
  { tag: "own" },
  { tag: "kind", when: { tag: "own", is: "yes" } },
  { tag: "years", when: { tag: "kind", is: "flat" } },
  { tag: "why", when: { tag: "own", is: "no" } },
  { tag: "end" },
];
const audit = (given) => auditBranchReplies({ items, given });

assert.deepEqual(
  audit({ own: "yes", kind: "flat", years: "3", end: "z" }),
  { due: ["own", "kind", "years", "end"], extra: [], gap: [] },
  "a branch taken all the way down owes every entry on it",
);
assert.deepEqual(
  audit({ own: "no", why: "cost", end: "z" }),
  { due: ["own", "why", "end"], extra: [], gap: [] },
  "the other branch owes its own entries and nothing else",
);
assert.deepEqual(
  audit({ own: "no", kind: "flat", years: "3", end: "z" }),
  { due: ["own", "why", "end"], extra: ["kind", "years"], gap: ["why"] },
  "an entry two levels under an untaken branch is spurious, not owed",
);
assert.deepEqual(
  audit({ own: "yes" }),
  { due: ["own", "kind", "end"], extra: [], gap: ["kind", "end"] },
  "an owed entry left empty is a gap",
);
assert.deepEqual(
  audit({}),
  { due: ["own", "end"], extra: [], gap: ["own", "end"] },
  "an empty sheet owes only its unguarded entries",
);
assert.deepEqual(
  audit({ own: "yes", kind: "house", end: "z" }),
  { due: ["own", "kind", "end"], extra: [], gap: [] },
  "a guard whose is does not match closes the branch below it",
);
assert.deepEqual(
  audit({ own: "no", kind: "flat", years: "3", why: "cost", end: "z" }),
  { due: ["own", "why", "end"], extra: ["kind", "years"], gap: [] },
  "spurious entries never turn into owed ones",
);

assert.throws(() => auditBranchReplies([]), Error, "a list is not a sheet");
assert.throws(() => auditBranchReplies({ items: [], given: {} }), Error, "no items at all");
assert.throws(
  () => auditBranchReplies({ items: [{ tag: "a" }, { tag: "a" }], given: {} }),
  Error,
  "two items may not share a tag",
);
assert.throws(
  () => auditBranchReplies({ items: [{ tag: "a", when: { tag: "b", is: "x" } }, { tag: "b" }], given: {} }),
  Error,
  "a when may not lean on a later item",
);
assert.throws(
  () => auditBranchReplies({ items: [{ tag: "a" }, { tag: "b", when: { tag: "a", is: "" } }], given: {} }),
  Error,
  "a when needs a non-empty is",
);
assert.throws(
  () => auditBranchReplies({ items: [{ tag: "a" }], given: { z: "x" } }),
  Error,
  "an answer to no item is refused",
);
assert.throws(
  () => auditBranchReplies({ items: [{ tag: "a" }], given: { a: 7 } }),
  Error,
  "an answer must be a string",
);
console.log("ok");
