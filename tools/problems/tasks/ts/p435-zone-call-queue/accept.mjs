import assert from "node:assert/strict";
import { buildZoneQueue } from "./solution.ts";

const one = (name, zone, party, early) => ({ name, zone, party, early });

assert.deepEqual(
  buildZoneQueue(
    ["gold", "one", "two"],
    [
      one("ada", "two", "", false),
      one("bo", "gold", "kin", false),
      one("cy", "two", "kin", false),
      one("di", "one", "", true),
      one("ed", "one", "", false),
    ],
  ),
  { queue: ["di", "bo", "cy", "ed", "ada"], calls: [2, 1, 1] },
  "the party walks with its earliest zone and is not called again",
);

assert.deepEqual(
  buildZoneQueue(
    ["a", "b"],
    [
      one("mo", "b", "fam", false),
      one("ny", "a", "fam", true),
      one("ox", "a", "", false),
    ],
  ),
  { queue: ["mo", "ny", "ox"], calls: [1, 0] },
  "one early traveller pre-boards the whole party",
);

assert.deepEqual(
  buildZoneQueue(
    ["z"],
    [one("zed", "z", "", false), one("abe", "z", "", false), one("mel", "z", "", false)],
  ),
  { queue: ["zed", "abe", "mel"], calls: [3] },
  "empty party strings never join and keep desk order",
);

assert.deepEqual(
  buildZoneQueue(
    ["z"],
    [one("zoe", "z", "", true), one("amy", "z", "", true)],
  ),
  { queue: ["amy", "zoe"], calls: [0] },
  "the pre-board block walks in name order, counting under no zone",
);

assert.deepEqual(
  buildZoneQueue(["p", "q"], []),
  { queue: [], calls: [0, 0] },
  "nobody at the desk still reports one count per zone",
);

assert.deepEqual(
  buildZoneQueue(
    ["first", "second"],
    [
      one("hal", "second", "trio", false),
      one("gus", "second", "", false),
      one("ivy", "first", "trio", false),
      one("fay", "second", "trio", false),
    ],
  ),
  { queue: ["fay", "hal", "ivy", "gus"], calls: [3, 1] },
  "a unit sorts its own members by name and is placed by its earliest member",
);

assert.deepEqual(
  buildZoneQueue(
    ["one", "two"],
    [
      one("kit", "two", "duo", false),
      one("lil", "one", "", false),
      one("nan", "two", "duo", false),
    ],
  ),
  { queue: ["lil", "kit", "nan"], calls: [1, 2] },
  "a later zone still calls the units waiting for it in desk order",
);

assert.throws(() => buildZoneQueue("gold", []), Error, "the zones must be a list");
assert.throws(() => buildZoneQueue(["a"], "x"), Error, "the travellers must be a list");
assert.throws(() => buildZoneQueue([], []), Error, "no zones at all is rejected");
assert.throws(() => buildZoneQueue(["a", ""], []), Error, "an empty zone label is rejected");
assert.throws(() => buildZoneQueue(["a", "a"], []), Error, "a repeated zone label is rejected");
assert.throws(() => buildZoneQueue(["a"], ["ada"]), Error, "a traveller must be a mapping");
assert.throws(() => buildZoneQueue(["a"], [one("", "a", "", false)]), Error, "an empty name is rejected");
assert.throws(
  () => buildZoneQueue(["a"], [one("sam", "a", "", false), one("sam", "a", "", false)]),
  Error,
  "a shared name is rejected",
);
assert.throws(() => buildZoneQueue(["a"], [one("sam", "a", 4, false)]), Error, "a non-string party is rejected");
assert.throws(() => buildZoneQueue(["a"], [one("sam", "a", "", "yes")]), Error, "a non-boolean early flag is rejected");
assert.throws(() => buildZoneQueue(["a"], [one("sam", "b", "", false)]), Error, "an uncalled zone is rejected");
assert.throws(() => buildZoneQueue(["a"], [{ zone: "a", party: "", early: false }]), Error, "a missing name is rejected");
console.log("ok");
