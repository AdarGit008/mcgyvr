import assert from "node:assert/strict";
import { translateStrandFrame } from "./solution.ts";

assert.deepEqual(
  translateStrandFrame("WWW"),
  { residues: "a", halted: false },
  "the first residue of the run",
);
assert.deepEqual(
  translateStrandFrame("XYZ"),
  { residues: "g", halted: false },
  "four times one plus two lands on g",
);
assert.deepEqual(
  translateStrandFrame("WWWXYZ"),
  { residues: "ag", halted: false },
  "two codons read in order",
);
assert.deepEqual(
  translateStrandFrame("WWWWWXWWYWWZ"),
  { residues: "aaaa", halted: false },
  "the third symbol never moves the residue",
);
assert.deepEqual(
  translateStrandFrame("ZWWZXWZYWZZY"),
  { residues: "mnop", halted: false },
  "the tail of the sixteen-letter run",
);
assert.deepEqual(
  translateStrandFrame("ZZW"),
  { residues: "", halted: true },
  "a halt marker on its own",
);
assert.deepEqual(
  translateStrandFrame("ZZX"),
  { residues: "", halted: true },
  "the other halt marker",
);
assert.deepEqual(
  translateStrandFrame("WWWZZXYYY"),
  { residues: "a", halted: true },
  "what follows a halt marker is never read",
);
assert.deepEqual(
  translateStrandFrame("ZZYZZZ"),
  { residues: "pp", halted: false },
  "a codon close to a halt marker still names a residue",
);
assert.deepEqual(
  translateStrandFrame("ZWXWWW"),
  { residues: "ma", halted: false },
  "no halt marker leaves halted false",
);
assert.throws(
  () => translateStrandFrame(3),
  Error,
  "a strand that is not a string is thrown out",
);
assert.throws(
  () => translateStrandFrame(""),
  Error,
  "an empty strand is thrown out",
);
assert.throws(
  () => translateStrandFrame("WWWW"),
  Error,
  "a length off the multiple of three is thrown out",
);
assert.throws(
  () => translateStrandFrame("WWA"),
  Error,
  "a symbol outside the four is thrown out",
);
assert.throws(
  () => translateStrandFrame("www"),
  Error,
  "lower case is thrown out",
);
console.log("ok");
