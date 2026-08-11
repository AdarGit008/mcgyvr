import assert from "node:assert/strict";
import { payout, settleAll } from "./solution.ts";

assert.equal(payout(10, 3), 30, "stake times odds");
assert.equal(payout(0, 5), 0, "nothing staked, nothing returned");
assert.equal(settleAll([{ stake: 10, odds: 3, won: true }]), 30, "one winner");
assert.equal(settleAll([{ stake: 10, odds: 3, won: false }]), 0, "one loser");
assert.equal(settleAll([]), 0, "no bets at all");
assert.equal(
  settleAll([
    { stake: 5, odds: 2, won: true },
    { stake: 5, odds: 2, won: false },
    { stake: 1, odds: 10, won: true },
  ]),
  20,
  "only the winners count",
);
assert.throws(() => payout(-1, 2), Error, "a negative stake is rejected");
console.log("ok");
