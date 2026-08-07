import assert from "node:assert/strict";
import { layPalletRow } from "./solution.ts";

const b = (name, alen, blen, mass, tender) => ({ name, alen, blen, mass, tender });

assert.deepEqual(
  layPalletRow([b("a", 10, 4, 5, false), b("b", 8, 4, 5, false)], { run: 30, span: 6, load: 100 }),
  { laid: ["a flat", "b flat"], skipped: [], run: 12, mass: 10 },
  "two boxes that fit as they come are laid as they come",
);
assert.deepEqual(
  layPalletRow([b("wide", 9, 3, 5, false)], { run: 5, span: 10, load: 100 }),
  { laid: ["wide turned"], skipped: [], run: 2, mass: 5 },
  "a quarter turn saves a box too long for the run",
);
assert.deepEqual(
  layPalletRow([b("wide", 9, 3, 5, true)], { run: 5, span: 10, load: 100 }),
  { laid: [], skipped: ["wide"], run: 5, mass: 0 },
  "a tender box is never turned, so it is passed over",
);
assert.deepEqual(
  layPalletRow([b("sq", 4, 3, 5, false)], { run: 10, span: 10, load: 100 }),
  { laid: ["sq flat"], skipped: [], run: 6, mass: 5 },
  "when both lies work the box goes down as it comes",
);
assert.deepEqual(
  layPalletRow(
    [b("a", 12, 5, 10, false), b("b", 9, 3, 10, false), b("c", 20, 20, 10, false), b("d", 4, 4, 10, false)],
    { run: 20, span: 8, load: 100 },
  ),
  { laid: ["a flat", "d flat"], skipped: ["b", "c"], run: 4, mass: 20 },
  "boxes behind a passed-over one are still tried",
);
assert.deepEqual(
  layPalletRow([b("a", 4, 4, 60, false), b("b", 4, 4, 60, false), b("c", 4, 4, 10, false)], { run: 40, span: 8, load: 100 }),
  { laid: ["a flat", "c flat"], skipped: ["b"], run: 32, mass: 70 },
  "the load rating passes over a heavy box and a lighter one still goes down",
);
assert.deepEqual(
  layPalletRow([b("a", 2, 9, 1, false)], { run: 40, span: 8, load: 100 }),
  { laid: ["a turned"], skipped: [], run: 31, mass: 1 },
  "a box too broad across the span is turned to run down the deck",
);
assert.deepEqual(
  layPalletRow([], { run: 5, span: 5, load: 5 }),
  { laid: [], skipped: [], run: 5, mass: 0 },
  "no boxes leaves the run untouched",
);
assert.deepEqual(
  layPalletRow([b("a", 5, 5, 5, false)], { run: 5, span: 5, load: 5 }),
  { laid: ["a flat"], skipped: [], run: 0, mass: 5 },
  "a box sitting exactly on every rating goes down",
);
assert.deepEqual(
  layPalletRow([b("a", 1, 1, 1, false)], { run: 5, span: 5, load: 0 }),
  { laid: [], skipped: ["a"], run: 5, mass: 0 },
  "a load rating of nought takes nothing at all",
);
assert.deepEqual(
  layPalletRow([b("p", 7, 2, 1, false), b("q", 2, 2, 1, false)], { run: 4, span: 8, load: 10 }),
  { laid: ["p turned", "q flat"], skipped: [], run: 0, mass: 2 },
  "a turned box eats only its short side of the run",
);

assert.throws(() => layPalletRow("no", { run: 1, span: 1, load: 1 }), Error, "boxes that are not a list are refused");
assert.throws(() => layPalletRow([], 7), Error, "a deck that is not a record is refused");
assert.throws(() => layPalletRow([], { run: 0, span: 1, load: 1 }), Error, "a run of nought is refused");
assert.throws(() => layPalletRow([], { run: 1, span: 1.5, load: 1 }), Error, "a fractional span is refused");
assert.throws(() => layPalletRow([], { run: 1, span: 1, load: -1 }), Error, "a negative load rating is refused");
assert.throws(() => layPalletRow([], { run: 1, span: 1 }), Error, "a missing load rating is refused");
assert.throws(() => layPalletRow([[1, 2]], { run: 1, span: 1, load: 1 }), Error, "a box that is not a record is refused");
assert.throws(() => layPalletRow([b("", 1, 1, 1, false)], { run: 1, span: 1, load: 1 }), Error, "an empty name is refused");
assert.throws(
  () => layPalletRow([b("a", 1, 1, 1, false), b("a", 2, 2, 2, false)], { run: 9, span: 9, load: 9 }),
  Error,
  "two boxes answering to one name are refused",
);
assert.throws(() => layPalletRow([b("a", 0, 1, 1, false)], { run: 1, span: 1, load: 1 }), Error, "a side of nought is refused");
assert.throws(
  () => layPalletRow([b("a", 1, 1, 1.5, false)], { run: 1, span: 1, load: 1 }),
  Error,
  "a fractional mass is refused",
);
assert.throws(() => layPalletRow([b("a", 1, 1, 1, 0)], { run: 1, span: 1, load: 1 }), Error, "a tender flag that is not a boolean is refused");
console.log("ok");
