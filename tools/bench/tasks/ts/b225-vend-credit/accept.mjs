import assert from "node:assert/strict";
import { vendCredit } from "./solution.ts";

assert.equal(vendCredit([], 25), 0, "no coins leaves no credit");
assert.equal(vendCredit([25], 25), 0, "one coin at the price drops an item and clears");
assert.equal(vendCredit([10, 10], 25), 20, "credit short of the price stands");
assert.equal(vendCredit([10, 10, 10], 25), 5, "the coin that reaches the price leaves change standing");
assert.equal(vendCredit([100], 30), 10, "one coin drops several items");
assert.equal(vendCredit([5, 100], 40), 25, "earlier credit counts toward the drops");
assert.equal(vendCredit([5, 5, 5, 5, 5], 5), 0, "every coin drops its own item");
assert.throws(() => vendCredit([50], 25), Error, "a coin the acceptor refuses is rejected");
assert.throws(() => vendCredit([], 0), Error, "a price of zero is rejected");
assert.throws(() => vendCredit([], 2.5), Error, "a fractional price is rejected");
assert.throws(() => vendCredit([], 7), Error, "a price off the five-cent step is rejected");
console.log("ok");
