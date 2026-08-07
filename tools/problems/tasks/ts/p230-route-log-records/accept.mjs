import assert from "node:assert/strict";
import { routeLogRecords } from "./solution.ts";

const RULES = [
  { sink: "audit", least: "info", tag: "billing", stop: false },
  { sink: "pager", least: "error", tag: "", stop: true },
  { sink: "file", least: "trace", tag: "", stop: false },
  { sink: "audit", least: "debug", tag: "", stop: false },
];

const SOUND = [{ sink: "a", least: "info", tag: "", stop: false }];
const ONE = [{ level: "info", tag: "" }];

assert.deepEqual(
  routeLogRecords(
    RULES,
    [
      { level: "info", tag: "billing" },
      { level: "error", tag: "billing" },
      { level: "trace", tag: "web" },
      { level: "fatal", tag: "web" },
      { level: "debug", tag: "billing" },
    ],
    "held",
  ),
  [
    { at: 0, sinks: ["audit", "file"] },
    { at: 1, sinks: ["audit", "pager"] },
    { at: 2, sinks: ["file"] },
    { at: 3, sinks: ["pager"] },
    { at: 4, sinks: ["file", "audit"] },
  ],
  "the whole rule list against five records at once",
);

assert.deepEqual(
  routeLogRecords([], ONE, "held"),
  [{ at: 0, sinks: ["held"] }],
  "with no rules at all everything falls to the spare",
);

assert.deepEqual(
  routeLogRecords([{ sink: "x", least: "error", tag: "", stop: false }], ONE, "held"),
  [{ at: 0, sinks: ["held"] }],
  "a record below every floor falls to the spare",
);

assert.deepEqual(
  routeLogRecords(
    [
      { sink: "a", least: "trace", tag: "", stop: false },
      { sink: "a", least: "trace", tag: "", stop: false },
    ],
    ONE,
    "held",
  ),
  [{ at: 0, sinks: ["a"] }],
  "one sink named by two rules is added once",
);

assert.deepEqual(
  routeLogRecords(
    [
      { sink: "a", least: "trace", tag: "", stop: true },
      { sink: "b", least: "trace", tag: "", stop: false },
    ],
    ONE,
    "held",
  ),
  [{ at: 0, sinks: ["a"] }],
  "a stopping rule shuts out the rules behind it",
);

assert.deepEqual(
  routeLogRecords(
    [{ sink: "a", least: "trace", tag: "web", stop: false }],
    [
      { level: "fatal", tag: "web" },
      { level: "fatal", tag: "webs" },
      { level: "fatal", tag: "" },
    ],
    "held",
  ),
  [
    { at: 0, sinks: ["a"] },
    { at: 1, sinks: ["held"] },
    { at: 2, sinks: ["held"] },
  ],
  "a rule's tag must be the record's tag exactly",
);

assert.deepEqual(
  routeLogRecords(
    [{ sink: "a", least: "warn", tag: "", stop: false }],
    [
      { level: "info", tag: "" },
      { level: "warn", tag: "" },
      { level: "error", tag: "" },
    ],
    "held",
  ),
  [
    { at: 0, sinks: ["held"] },
    { at: 1, sinks: ["a"] },
    { at: 2, sinks: ["a"] },
  ],
  "the floor takes in the level it names",
);

assert.deepEqual(routeLogRecords(RULES, [], "held"), [], "no records make no rows");

assert.throws(() => routeLogRecords("rules", ONE, "held"), Error, "rules that are not a list are rejected");
assert.throws(() => routeLogRecords(SOUND, "records", "held"), Error, "records that are not a list are rejected");
assert.throws(() => routeLogRecords([["a"]], ONE, "held"), Error, "a rule that is not a mapping is rejected");
assert.throws(
  () => routeLogRecords([{ sink: "", least: "info", tag: "", stop: false }], ONE, "held"),
  Error,
  "an empty sink name is rejected",
);
assert.throws(
  () => routeLogRecords([{ sink: "a", least: "loud", tag: "", stop: false }], ONE, "held"),
  Error,
  "a rule naming no known level is rejected",
);
assert.throws(
  () => routeLogRecords([{ sink: "a", least: "info", tag: 5, stop: false }], ONE, "held"),
  Error,
  "a tag that is not a string is rejected",
);
assert.throws(
  () => routeLogRecords([{ sink: "a", least: "info", tag: "", stop: "yes" }], ONE, "held"),
  Error,
  "a stop that is not a boolean is rejected",
);
assert.throws(() => routeLogRecords(SOUND, [["info"]], "held"), Error, "a record that is not a mapping is rejected");
assert.throws(() => routeLogRecords(SOUND, [{ level: "loud", tag: "" }], "held"), Error, "a record naming no known level is rejected");
assert.throws(() => routeLogRecords(SOUND, [{ level: "info", tag: 9 }], "held"), Error, "a record tag that is not a string is rejected");
assert.throws(() => routeLogRecords(SOUND, ONE, ""), Error, "an empty spare name is rejected");
assert.throws(() => routeLogRecords(SOUND, ONE, 3), Error, "a spare name that is not a string is rejected");
console.log("ok");
