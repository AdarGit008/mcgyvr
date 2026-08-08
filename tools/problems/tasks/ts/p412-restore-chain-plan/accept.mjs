import assert from "node:assert/strict";
import { planRestoreChain } from "./solution.ts";

const run = (label, kind, step, sound) => ({ label, kind, step, sound });

const mixed = [
  run("mon", "full", 0, true),
  run("tue", "incr", 1, true),
  run("wed", "diff", 2, true),
  run("thu", "incr", 3, true),
  run("fri", "incr", 4, true),
];

assert.deepEqual(
  planRestoreChain(mixed, 0),
  { ok: "yes", chain: ["mon"], reason: "" },
  "a full run stands alone",
);
assert.deepEqual(
  planRestoreChain(mixed, 1),
  { ok: "yes", chain: ["mon", "tue"], reason: "" },
  "an incr run takes whatever sits directly before it",
);
assert.deepEqual(
  planRestoreChain(mixed, 2),
  { ok: "yes", chain: ["mon", "wed"], reason: "" },
  "a diff run skips straight to the full run",
);
assert.deepEqual(
  planRestoreChain(mixed, 4),
  { ok: "yes", chain: ["mon", "wed", "thu", "fri"], reason: "" },
  "two incr runs land on the diff and shorten the stack",
);
assert.deepEqual(
  planRestoreChain([...mixed].reverse(), 4),
  { ok: "yes", chain: ["mon", "wed", "thu", "fri"], reason: "" },
  "the order the runs arrive in changes nothing",
);

const twoFulls = [
  run("base", "full", 0, true),
  run("cut1", "diff", 1, true),
  run("rest", "full", 2, true),
  run("cut2", "diff", 3, true),
];
assert.deepEqual(
  planRestoreChain(twoFulls, 3),
  { ok: "yes", chain: ["rest", "cut2"], reason: "" },
  "a diff run pairs with the newest full run, not the oldest",
);

const spoiltFull = [
  run("base", "full", 0, true),
  run("rest", "full", 2, false),
  run("cut2", "diff", 3, true),
];
assert.deepEqual(
  planRestoreChain(spoiltFull, 3),
  { ok: "yes", chain: ["base", "cut2"], reason: "" },
  "an unreadable full run is stepped over for an older sound one",
);

const spoiltMiddle = [
  run("mon", "full", 0, true),
  run("wed", "diff", 2, false),
  run("thu", "incr", 3, true),
];
assert.deepEqual(
  planRestoreChain(spoiltMiddle, 3),
  { ok: "no", chain: [], reason: "damaged" },
  "an incr run cannot step over an unreadable predecessor",
);
assert.deepEqual(
  planRestoreChain(spoiltMiddle, 2),
  { ok: "no", chain: [], reason: "damaged" },
  "a target that is itself unreadable reports damaged",
);
assert.deepEqual(
  planRestoreChain([run("only", "diff", 7, true)], 7),
  { ok: "no", chain: [], reason: "nofull" },
  "a diff run with nothing before it is unreachable",
);
assert.deepEqual(
  planRestoreChain(
    [run("dud", "full", 0, false), run("late", "diff", 1, true)],
    1,
  ),
  { ok: "no", chain: [], reason: "nofull" },
  "a diff run whose only full run is unreadable is unreachable",
);
assert.deepEqual(
  planRestoreChain(
    [run("a", "incr", 4, true), run("b", "incr", 5, true)],
    5,
  ),
  { ok: "no", chain: [], reason: "nofull" },
  "a walk that runs off the start without a full run is unreachable",
);

assert.throws(() => planRestoreChain([], 0), Error, "an empty list is rejected");
assert.throws(() => planRestoreChain("mon", 0), Error, "a string is rejected");
assert.throws(
  () => planRestoreChain([{ label: "mon", kind: "full", step: 0 }], 0),
  Error,
  "a run without sound is rejected",
);
assert.throws(
  () => planRestoreChain([run("", "full", 0, true)], 0),
  Error,
  "an empty label is rejected",
);
assert.throws(
  () => planRestoreChain([run("mon", "full", 0, true), run("mon", "incr", 1, true)], 1),
  Error,
  "a repeated label is rejected",
);
assert.throws(
  () => planRestoreChain([run("mon", "full", 0, true), run("tue", "incr", 0, true)], 0),
  Error,
  "a repeated step is rejected",
);
assert.throws(
  () => planRestoreChain([run("mon", "clone", 0, true)], 0),
  Error,
  "an unknown kind is rejected",
);
assert.throws(
  () => planRestoreChain([run("mon", "full", -1, true)], -1),
  Error,
  "a negative step is rejected",
);
assert.throws(
  () => planRestoreChain([run("mon", "full", 0, "yes")], 0),
  Error,
  "a sound flag that is a word is rejected",
);
assert.throws(
  () => planRestoreChain(mixed, 9),
  Error,
  "a target no run carries is rejected",
);
assert.throws(
  () => planRestoreChain(mixed, 1.5),
  Error,
  "a fractional target is rejected",
);
console.log("ok");
