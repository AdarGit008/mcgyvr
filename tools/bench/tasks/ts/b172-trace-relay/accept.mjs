import assert from "node:assert/strict";
import { traceRelay } from "./solution.ts";

const night = { gate: "dock", dock: "yard", yard: "" };
const feeder = { east: "hub", west: "hub", hub: "" };

assert.deepEqual(traceRelay(night, "gate"), ["gate", "dock", "yard"], "the whole night is walked from the first post");
assert.deepEqual(traceRelay(night, "dock"), ["dock", "yard"], "a start partway along walks only the rest");
assert.deepEqual(traceRelay(night, "yard"), ["yard"], "the last post walks alone");
assert.deepEqual(traceRelay({ solo: "" }, "solo"), ["solo"], "a one-post night is a one-name route");
assert.deepEqual(traceRelay(feeder, "west"), ["west", "hub"], "two posts may hand on to the same post");
assert.deepEqual(traceRelay(feeder, "east"), ["east", "hub"], "the other feeder post walks its own route");
assert.throws(() => traceRelay(["gate"], "gate"), Error, "links that are not a mapping are rejected");
assert.throws(() => traceRelay(night, "roof"), Error, "a start that is not a post is rejected");
assert.throws(() => traceRelay({ gate: "dock", dock: "roof" }, "gate"), Error, "a handoff to an unnamed post is rejected");
assert.throws(() => traceRelay({ bow: "stern", stern: "bow" }, "bow"), Error, "a watch that comes round again is rejected");
console.log("ok");
