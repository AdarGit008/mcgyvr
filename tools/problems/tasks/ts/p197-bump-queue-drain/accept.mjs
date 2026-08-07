import assert from "node:assert/strict";
import { bumpQueueDrain } from "./solution.ts";

const t = (id, filed, grade) => ({ id, filed, grade });

assert.deepEqual(
  bumpQueueDrain([t("only", 0, 0)], 0, 4),
  ["only"],
  "one ticket is handled at the start minute"
);

assert.deepEqual(
  bumpQueueDrain([t("t1", 0, 2), t("t2", 0, 5)], 0, 4),
  ["t2", "t1"],
  "the heavier grade goes first when no bump has landed"
);

assert.deepEqual(
  bumpQueueDrain([t("A", 0, 0), t("B", 9, 2)], 9, 3),
  ["A", "B"],
  "three bumps carry a lowly ticket past a fresh heavier one"
);

assert.deepEqual(
  bumpQueueDrain([t("A", 0, 0), t("B", 0, 9)], 20, 1),
  ["A", "B"],
  "the ceiling flattens both urgencies so the id decides"
);

assert.deepEqual(
  bumpQueueDrain([t("A", 0, 1), t("B", 2, 9), t("C", 0, 0)], 0, 5),
  ["A", "C", "B"],
  "a ticket cannot be handled before the minute it was filed"
);

assert.deepEqual(
  bumpQueueDrain([t("A", 5, 1), t("B", 5, 3)], 0, 4),
  ["B", "A"],
  "minutes with nothing eligible pass by"
);

assert.deepEqual(
  bumpQueueDrain([t("A", 0, 3), t("B", 4, 4)], 4, 4),
  ["A", "B"],
  "equal urgency falls to the ticket filed earlier"
);

assert.deepEqual(
  bumpQueueDrain([t("zulu", 0, 2), t("alpha", 0, 2)], 0, 4),
  ["alpha", "zulu"],
  "equal urgency and equal filing falls to the id"
);

assert.throws(() => bumpQueueDrain([], 0, 4), Error, "an empty batch is rejected");
assert.throws(
  () => bumpQueueDrain(["t1"], 0, 4),
  Error,
  "a ticket that is not a mapping is rejected"
);
assert.throws(
  () => bumpQueueDrain([{ filed: 0, grade: 1 }], 0, 4),
  Error,
  "a ticket with no id is rejected"
);
assert.throws(
  () => bumpQueueDrain([t("dup", 0, 1), t("dup", 1, 2)], 0, 4),
  Error,
  "a repeated id is rejected"
);
assert.throws(
  () => bumpQueueDrain([t("A", -1, 1)], 0, 4),
  Error,
  "a negative filed minute is rejected"
);
assert.throws(
  () => bumpQueueDrain([t("A", 0, 10)], 0, 4),
  Error,
  "a grade above nine is rejected"
);
assert.throws(
  () => bumpQueueDrain([t("A", 0, 1)], -3, 4),
  Error,
  "a negative start minute is rejected"
);
assert.throws(
  () => bumpQueueDrain([t("A", 0, 1)], 0, 0),
  Error,
  "a bump interval of zero is rejected"
);

console.log("ok");
