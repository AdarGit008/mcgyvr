import assert from "node:assert/strict";
import { auditChain, sealOf } from "./solution.ts";

assert.equal(sealOf("cargo", 0), 6800, "seal of a note on a zero base");
assert.equal(sealOf("", 7), 7, "empty note keeps the base");
assert.deepEqual(auditChain([]), [], "empty trail is intact");
assert.deepEqual(
  auditChain([
    { seq: 1, note: "load", seal: 6197 },
    { seq: 2, note: "move", seal: 470 },
    { seq: 3, note: "drop", seal: 568 },
  ]),
  [],
  "an intact trail reports nothing",
);
assert.deepEqual(
  auditChain([
    { seq: 1, note: "load", seal: 6197 },
    { seq: 2, note: "mole", seal: 470 },
    { seq: 3, note: "drop", seal: 568 },
  ]),
  [2],
  "a reworded note flags only its record",
);
assert.deepEqual(
  auditChain([
    { seq: 1, note: "load", seal: 6197 },
    { seq: 2, note: "move", seal: 471 },
    { seq: 3, note: "drop", seal: 568 },
  ]),
  [2, 3],
  "a forged seal flags the next record too",
);
assert.deepEqual(
  auditChain([
    { seq: 1, note: "load", seal: 6202 },
    { seq: 2, note: "move", seal: 576 },
  ]),
  [1],
  "the opening seal is checked against zero",
);
assert.throws(() => auditChain("x"), Error, "non-list is rejected");
assert.throws(() => auditChain([{ seq: 1, note: "a" }]), Error, "a missing seal is rejected");
assert.throws(() => auditChain([{ seq: 1, note: 7, seal: 0 }]), Error, "a non-string note is rejected");
assert.throws(
  () =>
    auditChain([
      { seq: 1, note: "load", seal: 6197 },
      { seq: 3, note: "move", seal: 470 },
    ]),
  Error,
  "a seq gap is rejected",
);
assert.throws(() => auditChain([{ seq: 1, note: "load", seal: "6197" }]), Error, "a string seal is rejected");
console.log("ok");
