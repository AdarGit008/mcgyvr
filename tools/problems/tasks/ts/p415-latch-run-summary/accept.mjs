import assert from "node:assert/strict";
import { summariseLatchRun } from "./solution.ts";

assert.deepEqual(
  summariseLatchRun(
    ["bad", "good", "bad", "good", "good", "bad", "bad", "good", "good", "good"],
    { span: 3, sour: 2, wait: 2, trials: 2 },
  ),
  { mode: "shut", tried: 6, shed: 4, trips: 2 },
  "two trips, four shed steps, and the latch earns its way back",
);
assert.deepEqual(
  summariseLatchRun(["bad", "good", "good", "good", "bad"], {
    span: 3,
    sour: 2,
    wait: 1,
    trials: 1,
  }),
  { mode: "shut", tried: 5, shed: 0, trips: 0 },
  "the oldest word leaves the ledger, so an early bad cannot trip a later one",
);
assert.deepEqual(
  summariseLatchRun(["bad", "bad"], { span: 4, sour: 2, wait: 1, trials: 1 }),
  { mode: "shut", tried: 2, shed: 0, trips: 0 },
  "a ledger short of span never trips however sour it is",
);
assert.deepEqual(
  summariseLatchRun(["bad", "good", "good", "good", "good"], {
    span: 1,
    sour: 1,
    wait: 3,
    trials: 1,
  }),
  { mode: "shut", tried: 2, shed: 3, trips: 1 },
  "three steps pass with no call while the countdown runs",
);
assert.deepEqual(
  summariseLatchRun(["bad", "good"], { span: 1, sour: 1, wait: 5, trials: 1 }),
  { mode: "tripped", tried: 1, shed: 1, trips: 1 },
  "a run ending mid countdown reports the tripped mode",
);
assert.deepEqual(
  summariseLatchRun(["bad", "good", "bad", "bad", "good", "good"], {
    span: 2,
    sour: 2,
    wait: 1,
    trials: 1,
  }),
  { mode: "shut", tried: 5, shed: 1, trips: 1 },
  "the ledger is emptied on tripping, so it refills from scratch",
);
assert.deepEqual(
  summariseLatchRun([], { span: 2, sour: 1, wait: 1, trials: 1 }),
  { mode: "shut", tried: 0, shed: 0, trips: 0 },
  "an empty run leaves the latch untouched",
);
assert.deepEqual(
  summariseLatchRun(["good", "good", "good"], {
    span: 2,
    sour: 1,
    wait: 1,
    trials: 1,
  }),
  { mode: "shut", tried: 3, shed: 0, trips: 0 },
  "nothing bad ever trips the latch",
);

assert.throws(
  () => summariseLatchRun("bad", { span: 2, sour: 1, wait: 1, trials: 1 }),
  Error,
  "a run given as a string is rejected",
);
assert.throws(
  () => summariseLatchRun(["slow"], { span: 2, sour: 1, wait: 1, trials: 1 }),
  Error,
  "a word outside the two is rejected",
);
assert.throws(
  () => summariseLatchRun(["bad"], { span: 2, sour: 1, wait: 1 }),
  Error,
  "a dial without trials is rejected",
);
assert.throws(
  () => summariseLatchRun(["bad"], { span: 2, sour: 3, wait: 1, trials: 1 }),
  Error,
  "a sour larger than span is rejected",
);
assert.throws(
  () => summariseLatchRun(["bad"], { span: 0, sour: 1, wait: 1, trials: 1 }),
  Error,
  "a span of zero is rejected",
);
assert.throws(
  () => summariseLatchRun(["bad"], { span: 2, sour: 1, wait: 1.5, trials: 1 }),
  Error,
  "a fractional wait is rejected",
);
assert.throws(
  () => summariseLatchRun(["bad"], [2, 1, 1, 1]),
  Error,
  "a dial given as a list is rejected",
);
console.log("ok");
