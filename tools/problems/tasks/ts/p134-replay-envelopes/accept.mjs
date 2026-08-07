import assert from "node:assert/strict";
import { replayEnvelopes } from "./solution.ts";

const env = (name, monthly, cap) => ({ name, monthly, cap });

assert.deepEqual(
  replayEnvelopes([env("a", 100, 50)], [[]]),
  { balances: [["a", 50]], forfeited: 50 },
  "an over-cap close forfeits the excess",
);
assert.deepEqual(
  replayEnvelopes([env("a", 40, 20)], [[["a", 30]]]),
  { balances: [["a", 10]], forfeited: 0 },
  "deposit, then outlays, then cap — never cap before spending",
);
assert.deepEqual(
  replayEnvelopes([env("a", 10, 100)], [[["a", 25]], []]),
  { balances: [["a", -5]], forfeited: 0 },
  "debt carries in full and the next deposit lands on top of it",
);
assert.deepEqual(
  replayEnvelopes([env("a", 30, 100)], [[["a", 10]], []]),
  { balances: [["a", 50]], forfeited: 0 },
  "an under-cap balance rolls into the next month untouched",
);
assert.deepEqual(
  replayEnvelopes([env("b", 5, 99), env("a", 7, 99)], [[]]),
  {
    balances: [
      ["b", 5],
      ["a", 7],
    ],
    forfeited: 0,
  },
  "balances keep declaration order, not name order",
);
assert.deepEqual(
  replayEnvelopes([env("a", 60, 50)], [[], []]),
  { balances: [["a", 50]], forfeited: 70 },
  "forfeits accumulate month after month",
);
assert.deepEqual(
  replayEnvelopes([env("a", 9, 5)], []),
  { balances: [["a", 0]], forfeited: 0 },
  "no months means untouched zero balances",
);
assert.deepEqual(
  replayEnvelopes(
    [env("food", 50, 40), env("fun", 20, 100)],
    [
      [
        ["food", 30],
        ["fun", 5],
      ],
    ],
  ),
  {
    balances: [
      ["food", 20],
      ["fun", 15],
    ],
    forfeited: 0,
  },
  "outlays hit only the envelope they name",
);
assert.throws(
  () => replayEnvelopes([env("a", 5, 5)], [[["ghost", 1]]]),
  Error,
  "an outlay on an unknown envelope is rejected",
);
assert.throws(
  () => replayEnvelopes([env("a", 5, 5), env("a", 1, 1)], []),
  Error,
  "a duplicate envelope name is rejected",
);
assert.throws(
  () => replayEnvelopes([env("a", -5, 5)], []),
  Error,
  "a negative monthly is rejected",
);
assert.throws(
  () => replayEnvelopes([env("a", 5, 1.5)], []),
  Error,
  "a fractional cap is rejected",
);
assert.throws(
  () => replayEnvelopes([env("a", 5, 5)], [[["a", 0]]]),
  Error,
  "a zero outlay is rejected",
);
assert.throws(
  () => replayEnvelopes([env("", 5, 5)], []),
  Error,
  "an empty envelope name is rejected",
);
console.log("ok");
