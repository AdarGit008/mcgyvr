import assert from "node:assert/strict";
import { decideSwitch } from "./solution.ts";

const ramping = { mode: "ramp", barred: ["dee"], waved: ["ann"], cutoff: 30 };

assert.deepEqual(
  decideSwitch(ramping, { id: "dee", slot: 0 }),
  { open: "no", why: "barred" },
  "the barred list is read before anything else",
);
assert.deepEqual(
  decideSwitch(ramping, { id: "ann", slot: 99 }),
  { open: "yes", why: "waved" },
  "a waved caller ignores the ramp entirely",
);
assert.deepEqual(
  decideSwitch(ramping, { id: "bob", slot: 29 }),
  { open: "yes", why: "ramp" },
  "the last slot below the cutoff is let through",
);
assert.deepEqual(
  decideSwitch(ramping, { id: "bob", slot: 30 }),
  { open: "no", why: "held" },
  "a slot equal to the cutoff is held back",
);
assert.deepEqual(
  decideSwitch({ mode: "ramp", barred: [], waved: [], cutoff: 0 }, { id: "bob", slot: 0 }),
  { open: "no", why: "held" },
  "a cutoff of zero lets nobody onto the ramp",
);
assert.deepEqual(
  decideSwitch({ mode: "ramp", barred: [], waved: [], cutoff: 100 }, { id: "bob", slot: 99 }),
  { open: "yes", why: "ramp" },
  "a cutoff of a hundred takes the highest slot",
);

const dark = { mode: "dark", barred: ["dee"], waved: ["ann"], cutoff: 100 };
assert.deepEqual(
  decideSwitch(dark, { id: "ann", slot: 0 }),
  { open: "no", why: "dark" },
  "dark outranks the waved list",
);
assert.deepEqual(
  decideSwitch(dark, { id: "dee", slot: 0 }),
  { open: "no", why: "barred" },
  "barred still outranks dark",
);

const live = { mode: "live", barred: ["dee"], waved: ["ann"], cutoff: 0 };
assert.deepEqual(
  decideSwitch(live, { id: "bob", slot: 99 }),
  { open: "yes", why: "live" },
  "live ignores the cutoff",
);
assert.deepEqual(
  decideSwitch(live, { id: "ann", slot: 99 }),
  { open: "yes", why: "waved" },
  "the waved list is read before the mode",
);
assert.deepEqual(
  decideSwitch(live, { id: "dee", slot: 0 }),
  { open: "no", why: "barred" },
  "barred outranks live too",
);

assert.throws(
  () => decideSwitch({ mode: "off", barred: [], waved: [], cutoff: 0 }, { id: "bob", slot: 0 }),
  Error,
  "an unknown mode is rejected",
);
assert.throws(
  () => decideSwitch({ mode: "ramp", barred: [], waved: [], cutoff: 101 }, { id: "bob", slot: 0 }),
  Error,
  "a cutoff past a hundred is rejected",
);
assert.throws(
  () => decideSwitch({ mode: "ramp", barred: [], waved: [], cutoff: -1 }, { id: "bob", slot: 0 }),
  Error,
  "a negative cutoff is rejected",
);
assert.throws(
  () => decideSwitch({ mode: "ramp", barred: "dee", waved: [], cutoff: 0 }, { id: "bob", slot: 0 }),
  Error,
  "a barred list that is a string is rejected",
);
assert.throws(
  () =>
    decideSwitch(
      { mode: "ramp", barred: ["dee", "dee"], waved: [], cutoff: 0 },
      { id: "bob", slot: 0 },
    ),
  Error,
  "one id named twice in a list is rejected",
);
assert.throws(
  () =>
    decideSwitch(
      { mode: "ramp", barred: ["ann"], waved: ["ann"], cutoff: 0 },
      { id: "bob", slot: 0 },
    ),
  Error,
  "an id both barred and waved is rejected",
);
assert.throws(
  () => decideSwitch({ mode: "ramp", barred: [], cutoff: 0 }, { id: "bob", slot: 0 }),
  Error,
  "a setting without waved is rejected",
);
assert.throws(
  () => decideSwitch(ramping, { id: "bob", slot: 100 }),
  Error,
  "a slot of a hundred is rejected",
);
assert.throws(
  () => decideSwitch(ramping, { id: "", slot: 0 }),
  Error,
  "an empty id is rejected",
);
assert.throws(
  () => decideSwitch(ramping, { id: "bob" }),
  Error,
  "a caller without a slot is rejected",
);
console.log("ok");
