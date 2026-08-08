import assert from "node:assert/strict";
import { replayLoanDesk } from "./solution.ts";

assert.deepEqual(
  replayLoanDesk({ d: 1 }, 3, [
    ["borrow", "a", "d"],
    ["borrow", "b", "d"],
    ["hold", "b", "d"],
    ["hold", "c", "d"],
    ["hold", "b", "d"],
    ["renew", "a", "d"],
    ["return", "a", "d"],
    ["borrow", "c", "d"],
    ["borrow", "b", "d"],
    ["return", "b", "d"],
    ["borrow", "c", "d"],
  ]),
  [
    "ok",
    "no:none-left",
    "ok",
    "ok",
    "no:in-queue",
    "no:on-hold",
    "ok",
    "no:queued-ahead",
    "ok",
    "ok",
    "ok",
  ],
  "the hold queue gates who may borrow next",
);
assert.deepEqual(
  replayLoanDesk({ r: 1 }, 1, [
    ["borrow", "a", "r"],
    ["renew", "a", "r"],
    ["renew", "a", "r"],
    ["renew", "a", "r"],
    ["return", "a", "r"],
    ["borrow", "a", "r"],
    ["renew", "a", "r"],
  ]),
  ["ok", "ok", "ok", "no:renew-cap", "ok", "ok", "ok"],
  "two renewals per loan, reset by a fresh borrow",
);
assert.deepEqual(
  replayLoanDesk({ x: 1, y: 1, z: 1 }, 2, [
    ["borrow", "a", "x"],
    ["borrow", "a", "y"],
    ["borrow", "a", "z"],
    ["return", "b", "x"],
    ["renew", "b", "x"],
    ["borrow", "a", "q"],
    ["hold", "a", "x"],
    ["hold", "b", "y"],
    ["hold", "b", "z"],
  ]),
  [
    "ok",
    "ok",
    "no:member-cap",
    "no:not-out",
    "no:not-out",
    "no:unknown-title",
    "no:own-loan",
    "ok",
    "no:take-it",
  ],
  "member cap, holder checks and hold preconditions",
);
assert.deepEqual(
  replayLoanDesk({ m: 2 }, 5, [
    ["borrow", "a", "m"],
    ["borrow", "b", "m"],
    ["borrow", "c", "m"],
    ["hold", "c", "m"],
    ["return", "a", "m"],
    ["borrow", "d", "m"],
    ["borrow", "c", "m"],
  ]),
  ["ok", "ok", "no:none-left", "ok", "ok", "no:queued-ahead", "ok"],
  "two copies circulate through one queue",
);
assert.deepEqual(
  replayLoanDesk({ s: 1 }, 1, [["borrow", "a", "s"], ["borrow", "a", "s"]]),
  ["ok", "no:already-out"],
  "already-out beats member-cap in check order",
);
assert.deepEqual(replayLoanDesk({ s: 1 }, 1, []), [], "no events, no answers");
assert.throws(
  () => replayLoanDesk({ s: 1 }, 1, [["steal", "a", "s"]]),
  Error,
  "unknown action throws",
);
assert.throws(
  () => replayLoanDesk({ s: 0 }, 1, []),
  Error,
  "zero copies throws",
);
assert.throws(() => replayLoanDesk({ s: 1 }, 0, []), Error, "zero cap throws");
assert.throws(
  () => replayLoanDesk({ s: 1 }, 1, [["borrow", "a"]]),
  Error,
  "short event throws",
);
console.log("ok");
