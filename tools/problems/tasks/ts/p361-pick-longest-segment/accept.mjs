import assert from "node:assert/strict";
import { pickLongestSegment } from "./solution.ts";

assert.deepEqual(
  pickLongestSegment("ZWXWWWZZW"),
  { frame: 0, start: 0, residues: "ma" },
  "one segment shutting on a closing marker",
);
assert.deepEqual(
  pickLongestSegment("ZWXZZW"),
  { frame: 0, start: 0, residues: "m" },
  "the opening marker alone still names m",
);
assert.deepEqual(
  pickLongestSegment("ZWXZWXWWWZZW"),
  { frame: 0, start: 0, residues: "mma" },
  "an opening marker inside a segment reads as a residue too",
);
assert.deepEqual(
  pickLongestSegment("WZWXWWWXYZZZX"),
  { frame: 1, start: 1, residues: "mag" },
  "the win sits in the second frame",
);
assert.deepEqual(
  pickLongestSegment("WWZWXXYZZZWWWW"),
  { frame: 2, start: 2, residues: "mg" },
  "the win sits in the third frame",
);
assert.deepEqual(
  pickLongestSegment("ZWXWWWZZWZWXXYZWWWZZX"),
  { frame: 0, start: 9, residues: "mga" },
  "the later segment is the longer one",
);
assert.deepEqual(
  pickLongestSegment("WZWXZZWWWZWXZZW"),
  { frame: 0, start: 9, residues: "m" },
  "equal lengths hand it to the smaller frame",
);
assert.deepEqual(
  pickLongestSegment("ZWXWWWZZWZWXWWWZZW"),
  { frame: 0, start: 0, residues: "ma" },
  "equal lengths in one frame hand it to the smaller start",
);
assert.deepEqual(
  pickLongestSegment("ZWXWWW"),
  { frame: -1, start: -1, residues: "" },
  "a segment that never shuts is thrown away",
);
assert.deepEqual(
  pickLongestSegment("WWW"),
  { frame: -1, start: -1, residues: "" },
  "a strand with no opening marker",
);
assert.deepEqual(
  pickLongestSegment("ZZWZZX"),
  { frame: -1, start: -1, residues: "" },
  "closing markers with nothing opened",
);
assert.throws(
  () => pickLongestSegment(7),
  Error,
  "a strand that is not a string is thrown out",
);
assert.throws(
  () => pickLongestSegment(""),
  Error,
  "an empty strand is thrown out",
);
assert.throws(
  () => pickLongestSegment("WWA"),
  Error,
  "a symbol outside the four is thrown out",
);
assert.throws(
  () => pickLongestSegment("zwx"),
  Error,
  "lower case is thrown out",
);
console.log("ok");
