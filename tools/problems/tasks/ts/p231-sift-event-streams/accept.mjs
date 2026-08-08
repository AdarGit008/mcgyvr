import assert from "node:assert/strict";
import { siftEventStreams } from "./solution.ts";

const LANES = [
  { name: "quiet", prefix: "app.", upTo: "notice", last: false },
  { name: "watch", prefix: "", upTo: "alarm", last: false },
  { name: "quiet", prefix: "db.", upTo: "notice", last: false },
  { name: "sink", prefix: "app.", upTo: "panic", last: true },
];

const SOUND = [{ name: "a", prefix: "", upTo: "panic", last: false }];
const ONE = [{ channel: "x", severity: "chatter" }];

assert.deepEqual(
  siftEventStreams(LANES, [
    { channel: "app.web", severity: "chatter" },
    { channel: "db.main", severity: "notice" },
    { channel: "app.web", severity: "panic" },
    { channel: "other", severity: "panic" },
    { channel: "app.api", severity: "alarm" },
  ]),
  {
    lanes: [
      { name: "quiet", took: [0, 1] },
      { name: "watch", took: [0, 1, 4] },
      { name: "sink", took: [0, 2, 4] },
    ],
    dropped: [3],
  },
  "four lanes over five events, names folded and one event dropped",
);

assert.deepEqual(
  siftEventStreams(
    [
      { name: "a", prefix: "", upTo: "panic", last: false },
      { name: "a", prefix: "", upTo: "panic", last: false },
    ],
    ONE,
  ),
  { lanes: [{ name: "a", took: [0] }], dropped: [] },
  "two lanes of one name take the event once between them",
);

assert.deepEqual(
  siftEventStreams(
    [
      { name: "a", prefix: "", upTo: "panic", last: true },
      { name: "b", prefix: "", upTo: "panic", last: false },
    ],
    ONE,
  ),
  {
    lanes: [
      { name: "a", took: [0] },
      { name: "b", took: [] },
    ],
    dropped: [],
  },
  "a final lane leaves the one behind it empty",
);

assert.deepEqual(
  siftEventStreams(
    [{ name: "a", prefix: "", upTo: "notice", last: false }],
    [
      { channel: "x", severity: "chatter" },
      { channel: "x", severity: "notice" },
      { channel: "x", severity: "alarm" },
    ],
  ),
  { lanes: [{ name: "a", took: [0, 1] }], dropped: [2] },
  "the ceiling takes in the severity it names and nothing above it",
);

assert.deepEqual(
  siftEventStreams(
    [{ name: "a", prefix: "app.", upTo: "panic", last: false }],
    [
      { channel: "app", severity: "panic" },
      { channel: "app.", severity: "panic" },
      { channel: "application", severity: "panic" },
    ],
  ),
  { lanes: [{ name: "a", took: [1] }], dropped: [0, 2] },
  "a prefix is matched at the opening of the channel, letter for letter",
);

assert.deepEqual(
  siftEventStreams([], ONE),
  { lanes: [], dropped: [0] },
  "with no lanes every event is dropped",
);

assert.deepEqual(
  siftEventStreams(LANES, []),
  {
    lanes: [
      { name: "quiet", took: [] },
      { name: "watch", took: [] },
      { name: "sink", took: [] },
    ],
    dropped: [],
  },
  "with no events the lanes are still named, all empty",
);

assert.throws(() => siftEventStreams("lanes", ONE), Error, "lanes that are not a list are rejected");
assert.throws(() => siftEventStreams(SOUND, "events"), Error, "events that are not a list are rejected");
assert.throws(() => siftEventStreams([["a"]], ONE), Error, "a lane that is not a mapping is rejected");
assert.throws(
  () => siftEventStreams([{ name: "", prefix: "", upTo: "panic", last: false }], ONE),
  Error,
  "an empty lane name is rejected",
);
assert.throws(
  () => siftEventStreams([{ name: "a", prefix: 4, upTo: "panic", last: false }], ONE),
  Error,
  "a prefix that is not a string is rejected",
);
assert.throws(
  () => siftEventStreams([{ name: "a", prefix: "", upTo: "loud", last: false }], ONE),
  Error,
  "a lane naming no known severity is rejected",
);
assert.throws(
  () => siftEventStreams([{ name: "a", prefix: "", upTo: "panic", last: "yes" }], ONE),
  Error,
  "a last that is not a boolean is rejected",
);
assert.throws(() => siftEventStreams(SOUND, [["x"]]), Error, "an event that is not a mapping is rejected");
assert.throws(
  () => siftEventStreams(SOUND, [{ channel: "", severity: "panic" }]),
  Error,
  "an empty channel is rejected",
);
assert.throws(
  () => siftEventStreams(SOUND, [{ channel: "x", severity: "loud" }]),
  Error,
  "an event naming no known severity is rejected",
);
assert.throws(
  () => siftEventStreams(SOUND, [{ channel: 7, severity: "panic" }]),
  Error,
  "a channel that is not a string is rejected",
);
console.log("ok");
