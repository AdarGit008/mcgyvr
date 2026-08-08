import assert from "node:assert/strict";
import { tallyBallots } from "./solution.ts";

assert.deepEqual(tallyBallots([]), {}, "no events, empty tally");

assert.deepEqual(
  tallyBallots([
    { type: "cast", voter: "v1", option: "tea" },
    { type: "cast", voter: "v2", option: "tea" },
    { type: "cast", voter: "v3", option: "coffee" },
  ]),
  { tea: 2, coffee: 1 },
  "standing votes are counted per option"
);

assert.deepEqual(
  tallyBallots([
    { type: "cast", voter: "v1", option: "tea" },
    { type: "retract", voter: "v1" },
  ]),
  { tea: 0 },
  "a fully retracted option still appears at zero"
);

assert.deepEqual(
  tallyBallots([
    { type: "cast", voter: "v1", option: "tea" },
    { type: "retract", voter: "v1" },
    { type: "cast", voter: "v1", option: "coffee" },
    { type: "close" },
  ]),
  { tea: 0, coffee: 1 },
  "a voter may cast again after retracting"
);

assert.throws(
  () =>
    tallyBallots([
      { type: "cast", voter: "v1", option: "tea" },
      { type: "cast", voter: "v1", option: "coffee" },
    ]),
  Error,
  "casting over a standing vote is an error"
);

assert.throws(
  () => tallyBallots([{ type: "retract", voter: "v9" }]),
  Error,
  "retracting with no standing vote is an error"
);

assert.throws(
  () =>
    tallyBallots([
      { type: "close" },
      { type: "cast", voter: "v1", option: "tea" },
    ]),
  Error,
  "casting after close is an error"
);

assert.throws(
  () => tallyBallots([{ type: "close" }, { type: "close" }]),
  Error,
  "a second close is an error"
);

assert.throws(
  () => tallyBallots([{ type: "spoil", voter: "v1" }]),
  Error,
  "an unknown event type is an error"
);

console.log("ok");
