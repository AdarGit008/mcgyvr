import assert from "node:assert/strict";
import { countLaneSpan } from "./solution.ts";

assert.equal(countLaneSpan(["A:A"]), 1, "a claim on one lane counts one");
assert.equal(countLaneSpan(["A:C"]), 3, "both ends of a claim are kept");
assert.equal(countLaneSpan(["Z:AA"]), 2, "AA follows Z however the text sorts");
assert.equal(countLaneSpan(["A:Z", "AA:AB"]), 28, "two claims that abut");
assert.equal(countLaneSpan(["A:C", "E:F"]), 5, "two claims with a gap between");
assert.equal(countLaneSpan(["A:C", "B:E"]), 5, "overlapping claims merge");
assert.equal(countLaneSpan(["A:E", "B:C"]), 5, "a nested claim adds nothing");
assert.equal(countLaneSpan(["A:A", "A:A"]), 1, "the same claim twice counts once");
assert.equal(countLaneSpan(["C:E", "A:B"]), 5, "claims arrive out of order");
assert.equal(
  countLaneSpan(["B:D", "A:A", "F:G", "C:H"]),
  8,
  "four claims that knit into one run",
);
assert.equal(countLaneSpan(["A:ZZZ"]), 18278, "one claim over the whole sheet");
assert.throws(() => countLaneSpan("A:C"), Error, "a bare string is not a batch");
assert.throws(() => countLaneSpan([]), Error, "an empty batch is rejected");
assert.throws(() => countLaneSpan([5]), Error, "a number is not a claim");
assert.throws(() => countLaneSpan(["AC"]), Error, "a claim without a colon");
assert.throws(() => countLaneSpan(["A:B:C"]), Error, "a claim with two colons");
assert.throws(() => countLaneSpan([":C"]), Error, "a claim with a blank end");
assert.throws(() => countLaneSpan(["a:c"]), Error, "lower case is refused");
assert.throws(() => countLaneSpan(["AAAA:B"]), Error, "four capitals overrun");
assert.throws(() => countLaneSpan(["C:A"]), Error, "a backwards claim is refused");
console.log("ok");
