import assert from "node:assert/strict";
import { scanTapeLabel } from "./solution.ts";

assert.deepEqual(
  scanTapeLabel([212, 79, 1, 4, 0]),
  { major: 1, minor: 4, records: 0, extras: [] },
  "a shape-one label promising no records at all",
);
assert.deepEqual(
  scanTapeLabel([212, 79, 1, 3, 2, 1, 2, 3, 4, 5, 6]),
  { major: 1, minor: 3, records: 2, extras: [] },
  "two records three bytes wide follow a shape-one label",
);
assert.deepEqual(
  scanTapeLabel([212, 79, 2, 2, 3, 0, 1, 2, 3, 4, 5, 6]),
  { major: 2, minor: 2, records: 3, extras: [] },
  "a shape-two label may carry an empty extra table",
);
assert.deepEqual(
  scanTapeLabel([212, 79, 2, 1, 2, 1, 7, 0, 200, 8, 9]),
  { major: 2, minor: 1, records: 2, extras: [[7, 200]] },
  "one extra sits between the label and the records",
);
assert.deepEqual(
  scanTapeLabel([212, 79, 2, 2, 1, 3, 0, 0, 1, 5, 1, 0, 9, 255, 255, 6, 6]),
  { major: 2, minor: 2, records: 1, extras: [[0, 1], [5, 256], [9, 65535]] },
  "three extras are read in rising order of kind",
);
assert.deepEqual(
  scanTapeLabel([212, 79, 2, 9, 0, 1, 3, 0, 4]),
  { major: 2, minor: 9, records: 0, extras: [[3, 4]] },
  "an extra table with no records behind it",
);
assert.deepEqual(
  scanTapeLabel([212, 79, 1, 255, 1].concat(Array(255).fill(0))),
  { major: 1, minor: 255, records: 1, extras: [] },
  "the widest record the width byte can name",
);

assert.throws(() => scanTapeLabel(212), Error, "an argument that is not a list is refused");
assert.throws(() => scanTapeLabel([212, 79, 1, 1, 0, 300]), Error, "a value above 255 is refused");
assert.throws(() => scanTapeLabel([212, 79, 1, 1, -2]), Error, "a value below nought is refused");
assert.throws(() => scanTapeLabel([212, 79, 1, 1, 0.5]), Error, "a fractional value is refused");
assert.throws(() => scanTapeLabel([212, 79, 1, 4]), Error, "a run too short for the fixed part is refused");
assert.throws(() => scanTapeLabel([211, 79, 1, 4, 0]), Error, "a wrong opening byte is refused");
assert.throws(() => scanTapeLabel([212, 78, 1, 4, 0]), Error, "a wrong second byte is refused");
assert.throws(() => scanTapeLabel([212, 79, 3, 4, 0]), Error, "a major shape the reader lacks is refused");
assert.throws(() => scanTapeLabel([212, 79, 1, 0, 0]), Error, "a record width of nought is refused");
assert.throws(() => scanTapeLabel([212, 79, 2, 1, 0]), Error, "a shape-two run ending before the extra count is refused");
assert.throws(() => scanTapeLabel([212, 79, 2, 1, 0, 2, 1, 0, 0, 2, 0]), Error, "a run ending inside the extra table is refused");
assert.throws(() => scanTapeLabel([212, 79, 2, 1, 0, 2, 5, 0, 0, 5, 0, 0]), Error, "a repeated extra kind is refused");
assert.throws(() => scanTapeLabel([212, 79, 2, 1, 0, 2, 6, 0, 0, 2, 0, 0]), Error, "extras out of rising order are refused");
assert.throws(() => scanTapeLabel([212, 79, 1, 3, 2, 1, 2, 3, 4, 5]), Error, "a short run of records is refused");
assert.throws(() => scanTapeLabel([212, 79, 1, 3, 1, 1, 2, 3, 4]), Error, "a long run of records is refused");
assert.throws(
  () => scanTapeLabel([212, 79, 2, 5, 1, 1, 4, 0, 1, 0, 0]),
  Error,
  "the extra table's own bytes are never counted as records",
);
assert.throws(
  () => scanTapeLabel([212, 79, 2, 1, 0, 1, 7, 0, 200, 9, 9, 9]),
  Error,
  "bytes behind an extra table with no records are refused",
);
console.log("ok");
