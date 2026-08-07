import assert from "node:assert/strict";
import { settleReactionCounts } from "./solution.ts";

assert.deepEqual(
  settleReactionCounts([{ H: 2 }, { O: 2 }], [{ H: 2, O: 1 }]),
  [2, 1, 2],
  "three species settle at two, one, two",
);
assert.deepEqual(
  settleReactionCounts([{ N: 2 }, { H: 2 }], [{ N: 1, H: 3 }]),
  [1, 3, 2],
  "a multiplier of one is still reported",
);
assert.deepEqual(
  settleReactionCounts([{ Fe: 1 }, { O: 2 }], [{ Fe: 2, O: 3 }]),
  [4, 3, 2],
  "a two-letter symbol",
);
assert.deepEqual(
  settleReactionCounts(
    [{ C: 2, H: 6 }, { O: 2 }],
    [{ C: 1, O: 2 }, { H: 2, O: 1 }],
  ),
  [2, 7, 4, 6],
  "a multiplier past five is still in range",
);
assert.deepEqual(
  settleReactionCounts([{ C: 1 }, { H: 2 }], [{ C: 1, H: 4 }, { O: 2 }]),
  [],
  "a symbol only the right-hand side mentions blocks it",
);
assert.deepEqual(
  settleReactionCounts([{ H: 2, O: 1 }], [{ H: 2, O: 2 }]),
  [],
  "nothing in range settles it",
);
assert.deepEqual(
  settleReactionCounts(
    [{ C: 4, H: 10 }, { O: 2 }],
    [{ C: 1, O: 2 }, { H: 2, O: 1 }],
  ),
  [],
  "the least answer runs past ten",
);
assert.deepEqual(
  settleReactionCounts([{ H: 2, O: 1 }], [{ H: 2, O: 1 }]),
  [1, 1],
  "already settled",
);
assert.throws(
  () => settleReactionCounts({ H: 2 }, [{ H: 2 }]),
  Error,
  "the left-hand side is not a list",
);
assert.throws(
  () => settleReactionCounts([{ H: 2 }], "H2"),
  Error,
  "the right-hand side is not a list",
);
assert.throws(() => settleReactionCounts([], [{ H: 2 }]), Error, "an empty side");
assert.throws(() => settleReactionCounts([{ H: 2 }], []), Error, "the other side empty");
assert.throws(
  () => settleReactionCounts(["H2"], [{ H: 2 }]),
  Error,
  "a species that is not a mapping",
);
assert.throws(
  () => settleReactionCounts([{}], [{ H: 2 }]),
  Error,
  "a species mentioning nothing",
);
assert.throws(
  () => settleReactionCounts([{ h: 2 }], [{ h: 2 }]),
  Error,
  "a symbol with no capital",
);
assert.throws(
  () => settleReactionCounts([{ HE: 2 }], [{ HE: 2 }]),
  Error,
  "a symbol with two capitals",
);
assert.throws(
  () => settleReactionCounts([{ H: 0 }], [{ H: 1 }]),
  Error,
  "a holding of zero",
);
assert.throws(
  () => settleReactionCounts([{ H: "2" }], [{ H: 2 }]),
  Error,
  "a holding that is not a number",
);
assert.throws(
  () => settleReactionCounts([{ H: 1 }, { C: 1 }, { N: 1 }], [{ O: 1 }, { S: 1 }, { P: 1 }]),
  Error,
  "more than five species",
);
console.log("ok");
