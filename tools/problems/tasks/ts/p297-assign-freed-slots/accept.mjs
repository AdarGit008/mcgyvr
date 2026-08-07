import assert from "node:assert/strict";
import { assignFreedSlots } from "./solution.ts";

const one = (name, tier, waited, window) => ({ name, tier, waited, window });
const call = (slot, part) => ({ slot, part });

assert.deepEqual(assignFreedSlots([], []), [], "no calls, no placements");
assert.deepEqual(
  assignFreedSlots([one("eve", "urgent", 5, "afternoon")], [call("m9", "morning")]),
  [],
  "a slot nobody can take is passed over",
);
assert.deepEqual(
  assignFreedSlots(
    [one("fay", "soon", 1, "either")],
    [call("s1", "morning"), call("s2", "morning")],
  ),
  [{ slot: "s1", name: "fay" }],
  "a placed patient is off the list and takes no second slot",
);
assert.deepEqual(
  assignFreedSlots(
    [one("gil", "routine", 90, "either"), one("hen", "urgent", 1, "either")],
    [call("s1", "morning")],
  ),
  [{ slot: "s1", name: "hen" }],
  "urgent outranks ninety days of routine waiting",
);
assert.deepEqual(
  assignFreedSlots(
    [one("ida", "soon", 4, "either"), one("jay", "soon", 11, "either")],
    [call("s1", "afternoon")],
  ),
  [{ slot: "s1", name: "jay" }],
  "inside one tier the longer wait wins",
);
assert.deepEqual(
  assignFreedSlots(
    [one("kim", "soon", 7, "either"), one("lee", "soon", 7, "either")],
    [call("s1", "afternoon")],
  ),
  [{ slot: "s1", name: "kim" }],
  "a level pair goes to whoever stands nearer the front",
);
assert.deepEqual(
  assignFreedSlots(
    [
      one("ann", "routine", 40, "either"),
      one("bob", "urgent", 2, "morning"),
      one("cal", "soon", 30, "afternoon"),
      one("dee", "soon", 30, "either"),
    ],
    [
      call("m1", "morning"),
      call("a1", "afternoon"),
      call("a2", "afternoon"),
      call("m2", "morning"),
    ],
  ),
  [
    { slot: "m1", name: "bob" },
    { slot: "a1", name: "cal" },
    { slot: "a2", name: "dee" },
    { slot: "m2", name: "ann" },
  ],
  "four calls empty the standby list in tier order",
);
assert.deepEqual(
  assignFreedSlots(
    [one("mac", "urgent", 3, "morning"), one("nia", "routine", 0, "afternoon")],
    [call("a7", "afternoon")],
  ),
  [{ slot: "a7", name: "nia" }],
  "an urgent patient who cannot come that half-day is out of the running",
);

assert.throws(() => assignFreedSlots("x", []), Error, "the standby list is a list");
assert.throws(() => assignFreedSlots([], "x"), Error, "the calls are a list");
assert.throws(
  () => assignFreedSlots([one("pat", "later", 1, "either")], []),
  Error,
  "later is no tier",
);
assert.throws(
  () => assignFreedSlots([one("pat", "soon", 1, "evening")], []),
  Error,
  "evening is no window",
);
assert.throws(
  () => assignFreedSlots([one("pat", "soon", -2, "either")], []),
  Error,
  "waited is never negative",
);
assert.throws(
  () => assignFreedSlots([one("pat", "soon", 1, "either"), one("pat", "urgent", 2, "either")], []),
  Error,
  "two patients may not share a name",
);
assert.throws(
  () => assignFreedSlots([], [call("s1", "evening")]),
  Error,
  "a call names morning or afternoon",
);
assert.throws(
  () => assignFreedSlots([], [call("s1", "morning"), call("s1", "afternoon")]),
  Error,
  "two calls may not share a slot id",
);
console.log("ok");
