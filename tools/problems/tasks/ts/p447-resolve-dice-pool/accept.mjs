import assert from "node:assert/strict";
import { resolveDicePool } from "./solution.ts";

assert.deepEqual(
  resolveDicePool([{ sides: 6, dice: 4, keep: 3 }], [3, 6, 1, 5]),
  { totals: [14], dropped: [[2]] },
  "the three largest of four are held",
);
assert.deepEqual(
  resolveDicePool([{ sides: 6, dice: 3, keep: 1 }], [4, 4, 2]),
  { totals: [4], dropped: [[1, 2]] },
  "equal rolls give the place to the one drawn earlier",
);
assert.deepEqual(
  resolveDicePool(
    [
      { sides: 6, dice: 4, keep: 3 },
      { sides: 6, dice: 3, keep: 1 },
    ],
    [3, 6, 1, 5, 4, 4, 2],
  ),
  { totals: [14, 4], dropped: [[2], [5, 6]] },
  "positions are counted across the whole roll list",
);
assert.deepEqual(
  resolveDicePool([{ sides: 4, dice: 2, keep: 2 }], [1, 4]),
  { totals: [5], dropped: [[]] },
  "a pool that holds everything sets nothing aside",
);
assert.deepEqual(
  resolveDicePool([{ sides: 20, dice: 1, keep: 1 }], [13]),
  { totals: [13], dropped: [[]] },
  "a single die",
);
assert.deepEqual(
  resolveDicePool([{ sides: 6, dice: 4, keep: 2 }], [5, 5, 5, 1]),
  { totals: [10], dropped: [[2, 3]] },
  "three equal rolls and only two places",
);
assert.deepEqual(
  resolveDicePool([{ sides: 3, dice: 3, keep: 2 }], [3, 1, 3]),
  { totals: [6], dropped: [[1]] },
  "an odd die size is allowed",
);

assert.throws(() => resolveDicePool(5, [1]), Error, "pools that are not a list are refused");
assert.throws(() => resolveDicePool([], []), Error, "an empty list of pools is refused");
assert.throws(
  () => resolveDicePool([{ sides: 6, dice: 2, keep: 3 }], [1, 2]),
  Error,
  "holding more dice than were thrown is refused",
);
assert.throws(
  () => resolveDicePool([{ sides: 6, dice: 2, keep: 0 }], [1, 2]),
  Error,
  "holding none is refused",
);
assert.throws(
  () => resolveDicePool([{ sides: 6, dice: 0, keep: 1 }], []),
  Error,
  "a pool of no dice is refused",
);
assert.throws(
  () => resolveDicePool([{ sides: 1, dice: 1, keep: 1 }], [1]),
  Error,
  "a one-sided die is refused",
);
assert.throws(
  () => resolveDicePool([{ sides: 6, dice: 1, keep: 1 }], [7]),
  Error,
  "a roll above the die size is refused",
);
assert.throws(
  () => resolveDicePool([{ sides: 6, dice: 1, keep: 1 }], [0]),
  Error,
  "a roll below one is refused",
);
assert.throws(
  () => resolveDicePool([{ sides: 6, dice: 1, keep: 1 }], [3.5]),
  Error,
  "a roll that is not whole is refused",
);
assert.throws(
  () => resolveDicePool([{ sides: 6, dice: 3, keep: 1 }], [1, 2]),
  Error,
  "running out of rolls is refused",
);
assert.throws(
  () => resolveDicePool([{ sides: 6, dice: 1, keep: 1 }], [1, 2]),
  Error,
  "a roll left undrawn is refused",
);
console.log("ok");
