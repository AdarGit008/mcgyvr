import assert from "node:assert/strict";
import { placeDonations } from "./solution.ts";

const req = (id, kind, from, to, urgent = false) => ({
  id,
  kind,
  from,
  to,
  urgent,
});
const lot = (id, kind, day) => ({ id, kind, day });

assert.deepEqual(
  placeDonations(
    [req("r1", "food", 0, 10), req("r2", "food", 0, 5)],
    [lot("l1", "food", 3), lot("l2", "food", 3)],
  ),
  [
    ["l1", "r2"],
    ["l2", "r1"],
  ],
  "the sooner-closing span wins, and a served request closes",
);
assert.deepEqual(
  placeDonations(
    [req("slow", "food", 0, 10, true), req("fast", "food", 0, 5)],
    [lot("l1", "food", 2)],
  ),
  [["l1", "slow"]],
  "urgency outranks the sooner deadline",
);
assert.deepEqual(
  placeDonations(
    [req("r1", "food", 0, 5), req("r2", "food", 0, 5)],
    [lot("l1", "food", 1)],
  ),
  [["l1", "r1"]],
  "a full tie falls to the request listed first",
);
assert.deepEqual(
  placeDonations([req("r1", "meds", 0, 9)], [lot("l1", "ANY", 4)]),
  [["l1", "r1"]],
  "an ANY lot fits a kind it does not name",
);
assert.deepEqual(
  placeDonations([req("r1", "meds", 0, 9)], [lot("l1", "fuel", 4)]),
  [],
  "a mismatched kind is discarded",
);
assert.deepEqual(
  placeDonations([req("r1", "food", 2, 6)], [
    lot("l1", "food", 1),
    lot("l2", "food", 7),
    lot("l3", "food", 6),
  ]),
  [["l3", "r1"]],
  "the span is inclusive and days outside it are discarded",
);
assert.deepEqual(
  placeDonations([req("r1", "food", 0, 3)], []),
  [],
  "no lots, nothing placed",
);
assert.deepEqual(
  placeDonations(
    [req("a", "kit", 0, 4), req("b", "kit", 0, 9, true)],
    [lot("x", "kit", 8), lot("y", "kit", 2), lot("z", "kit", 2)],
  ),
  [
    ["x", "b"],
    ["y", "a"],
  ],
  "pairs come back in lot scan order with leftovers discarded",
);
assert.throws(
  () =>
    placeDonations([req("r1", "food", 0, 3), req("r1", "kit", 0, 3)], []),
  Error,
  "a repeated request id is rejected",
);
assert.throws(
  () =>
    placeDonations(
      [req("r1", "food", 0, 3)],
      [lot("l1", "food", 1), lot("l1", "food", 2)],
    ),
  Error,
  "a repeated lot id is rejected",
);
assert.throws(
  () => placeDonations([req("r1", "food", 8, 3)], []),
  Error,
  "a span with from greater than to is rejected",
);
assert.throws(
  () => placeDonations([req("r1", "food", 0, 3)], [lot("l1", "food", "2")]),
  Error,
  "a non-integer day is rejected",
);
console.log("ok");
