import assert from "node:assert/strict";
import { sweepArenaBlocks } from "./solution.ts";

const slot = (size, links, cleanup) => ({ size, links, cleanup });

assert.deepEqual(
  sweepArenaBlocks([], []),
  { blocks: [], reclaimed: 0, cleanups: [] },
  "an empty arena frees nothing",
);
assert.deepEqual(
  sweepArenaBlocks([slot(8, [], null), slot(4, [], null)], [0, 1]),
  { blocks: [], reclaimed: 0, cleanups: [] },
  "an arena held whole yields no block",
);
assert.deepEqual(
  sweepArenaBlocks([slot(8, [], null), slot(4, [], null), slot(2, [], null)], []),
  { blocks: [[0, 14]], reclaimed: 14, cleanups: [] },
  "with no anchor the whole arena merges into one block",
);
assert.deepEqual(
  sweepArenaBlocks(
    [
      slot(8, [1], null),
      slot(4, [], null),
      slot(16, [], "close-file"),
      slot(32, [], null),
      slot(4, [0], "flush"),
    ],
    [0],
  ),
  { blocks: [[2, 52]], reclaimed: 52, cleanups: ["close-file", "flush"] },
  "three freed slots side by side make one block and two cleanups",
);
assert.deepEqual(
  sweepArenaBlocks(
    [
      slot(2, [2], null),
      slot(3, [], "a"),
      slot(5, [], null),
      slot(7, [], "b"),
      slot(1, [], null),
    ],
    [0],
  ),
  { blocks: [[1, 3], [3, 8]], reclaimed: 11, cleanups: ["a", "b"] },
  "a marked slot between two free stretches keeps the blocks apart",
);
assert.deepEqual(
  sweepArenaBlocks(
    [slot(4, [1], null), slot(4, [0], null), slot(9, [], "spill")],
    [1],
  ),
  { blocks: [[2, 9]], reclaimed: 9, cleanups: ["spill"] },
  "links are followed in both directions of a mutual pair",
);
assert.deepEqual(
  sweepArenaBlocks([slot(6, [], "only"), slot(1, [], null)], [1]),
  { blocks: [[0, 6]], reclaimed: 6, cleanups: ["only"] },
  "a block may open at slot zero",
);

assert.throws(() => sweepArenaBlocks("arena", []), Error, "an arena is a list");
assert.throws(
  () => sweepArenaBlocks([slot(1, [], null)], 0),
  Error,
  "the anchors are a list",
);
assert.throws(
  () => sweepArenaBlocks([slot(0, [], null)], []),
  Error,
  "a size of zero is no size",
);
assert.throws(
  () => sweepArenaBlocks([slot(4, [3], null)], []),
  Error,
  "slot 3 is outside a one-slot arena",
);
assert.throws(
  () => sweepArenaBlocks([slot(4, [], null)], [1]),
  Error,
  "an anchor must name a slot",
);
assert.throws(
  () => sweepArenaBlocks([slot(4, [], 7)], []),
  Error,
  "a cleanup is a name or null",
);
assert.throws(
  () => sweepArenaBlocks([slot(4, "none", null)], []),
  Error,
  "links must be a list",
);
console.log("ok");
