import assert from "node:assert/strict";
import { numberSections, sectionCount } from "./solution.ts";

const doc = [
  { heading: "Intro", children: [
    { heading: "Scope", children: [] },
    { heading: "Terms", children: [{ heading: "Symbols", children: [] }] },
  ] },
  { heading: "Methods", children: [] },
];
assert.deepEqual(numberSections([]), [], "an empty outline has no labels");
assert.deepEqual(numberSections([{ heading: "Solo", children: [] }]), ["1 Solo"], "a lone section is labelled 1");
assert.deepEqual(
  numberSections(doc),
  ["1 Intro", "1.1 Scope", "1.2 Terms", "1.2.1 Symbols", "2 Methods"],
  "nested sections take dotted labels in document order",
);
assert.equal(sectionCount(doc), 5, "every depth counts toward the section count");
assert.throws(() => numberSections("outline"), Error, "a non-list argument is rejected");
assert.throws(() => numberSections([42]), Error, "a non-mapping section is rejected");
assert.throws(() => numberSections([{ heading: "", children: [] }]), Error, "an empty heading is rejected");
assert.throws(() => numberSections([{ heading: "A" }]), Error, "a missing children list is rejected");
assert.throws(
  () => numberSections([{ heading: "A", children: [{ heading: 7, children: [] }] }]),
  Error,
  "a bad heading deep in the tree is rejected",
);
console.log("ok");
