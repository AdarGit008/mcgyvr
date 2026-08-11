import assert from "node:assert/strict";
import { mergeBookings } from "./solution.ts";

assert.equal(mergeBookings("9-11"), "9-11", "a lone slot comes back unchanged");
assert.equal(mergeBookings("9-11,10-12"), "9-12", "overlapping slots fuse");
assert.equal(mergeBookings("9-11,11-13"), "9-13", "slots touching at an hour fuse");
assert.equal(mergeBookings("14-15,9-11"), "9-11,14-15", "the plan comes back sorted by start hour");
assert.equal(mergeBookings("9-17,10-11"), "9-17", "a slot inside another is swallowed");
assert.equal(mergeBookings("0-24"), "0-24", "a whole-day slot is kept");
assert.throws(() => mergeBookings(911), Error, "a plan that is not a string is rejected");
assert.throws(() => mergeBookings(""), Error, "an empty plan is rejected");
assert.throws(() => mergeBookings("9to11"), Error, "a slot without a hyphen is rejected");
assert.throws(() => mergeBookings("11-9"), Error, "a slot ending before it starts is rejected");
assert.throws(() => mergeBookings("9-25"), Error, "an hour past 24 is rejected");
console.log("ok");
