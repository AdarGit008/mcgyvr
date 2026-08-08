import assert from "node:assert/strict";
import { reportLockChanges } from "./solution.ts";

const before = [
  { name: "same", version: "1.2.3", source: "reg-a", needs: ["log"] },
  { name: "core", version: "2.1", source: "reg-a", needs: ["log", "net"] },
  { name: "log", version: "0.9.9", source: "reg-a", needs: [] },
  { name: "net", version: "1.0+build.7", source: "reg-a", needs: ["log"] },
  { name: "old", version: "3.0", source: "reg-b", needs: [] },
  { name: "movehost", version: "4.0", source: "reg-a", needs: [] },
  { name: "rewire", version: "5.0", source: "reg-a", needs: ["a", "b"] },
  { name: "back", version: "2.0", source: "reg-a", needs: [] },
];
const after = [
  { name: "newbie", version: "0.1", source: "reg-d", needs: ["core"] },
  { name: "core", version: "2.1.0", source: "reg-a", needs: ["log", "net"] },
  { name: "log", version: "1.0", source: "reg-z", needs: ["x"] },
  { name: "net", version: "1.0+build.9", source: "reg-a", needs: ["log"] },
  { name: "same", version: "1.2.3", source: "reg-a", needs: ["log"] },
  { name: "movehost", version: "4.0", source: "reg-c", needs: [] },
  { name: "rewire", version: "5.0", source: "reg-a", needs: ["b", "c", "d"] },
  { name: "back", version: "1.0", source: "reg-a", needs: [] },
];

assert.deepEqual(
  reportLockChanges(before, after),
  {
    added: [{ name: "newbie", version: "0.1" }],
    dropped: [{ name: "old", version: "3.0" }],
    lifted: [{ name: "log", from: "0.9.9", to: "1.0" }],
    lowered: [{ name: "back", from: "2.0", to: "1.0" }],
    rebuilt: [
      { name: "core", from: "2.1", to: "2.1.0" },
      { name: "net", from: "1.0+build.7", to: "1.0+build.9" },
    ],
    moved: [{ name: "movehost", from: "reg-a", to: "reg-c" }],
    rewired: [{ name: "rewire", gained: ["c", "d"], lost: ["a"] }],
  },
  "all seven buckets over one record, and a lifted name reported only once",
);

assert.deepEqual(
  reportLockChanges([], []),
  {
    added: [],
    dropped: [],
    lifted: [],
    lowered: [],
    rebuilt: [],
    moved: [],
    rewired: [],
  },
  "two empty records report nothing anywhere",
);

assert.deepEqual(
  reportLockChanges(
    [{ name: "p", version: "1.0+aa", source: "one", needs: ["q"] }],
    [{ name: "p", version: "1+bb", source: "two", needs: ["r"] }],
  ),
  {
    added: [],
    dropped: [],
    lifted: [],
    lowered: [],
    rebuilt: [{ name: "p", from: "1.0+aa", to: "1+bb" }],
    moved: [{ name: "p", from: "one", to: "two" }],
    rewired: [{ name: "p", gained: ["r"], lost: ["q"] }],
  },
  "one name standing level may fall into all three of the further buckets",
);

assert.deepEqual(
  reportLockChanges(
    [{ name: "p", version: "1.0", source: "one", needs: ["a", "b"] }],
    [{ name: "p", version: "1.0", source: "one", needs: ["b", "a"] }],
  ),
  {
    added: [],
    dropped: [],
    lifted: [],
    lowered: [],
    rebuilt: [],
    moved: [],
    rewired: [],
  },
  "the needs are compared as a set, not in the order they were written",
);

assert.deepEqual(
  reportLockChanges(
    [{ name: "p", version: "1.9", source: "one", needs: [] }],
    [{ name: "p", version: "1.10", source: "two", needs: ["z"] }],
  ),
  {
    added: [],
    dropped: [],
    lifted: [{ name: "p", from: "1.9", to: "1.10" }],
    lowered: [],
    rebuilt: [],
    moved: [],
    rewired: [],
  },
  "a lifted name keeps its source and needs out of the report",
);

assert.deepEqual(
  reportLockChanges(
    [{ name: "p", version: "0.0.1", source: "one", needs: [] }],
    [
      { name: "b", version: "1.0", source: "one", needs: [] },
      { name: "a", version: "2.0", source: "one", needs: [] },
    ],
  ),
  {
    added: [
      { name: "a", version: "2.0" },
      { name: "b", version: "1.0" },
    ],
    dropped: [{ name: "p", version: "0.0.1" }],
    lifted: [],
    lowered: [],
    rebuilt: [],
    moved: [],
    rewired: [],
  },
  "every bucket is ordered by name ascending",
);

assert.throws(
  () => reportLockChanges("nope", []),
  Error,
  "a record that is not a list is rejected",
);
assert.throws(
  () =>
    reportLockChanges([{ name: "p", version: "1.0", source: "one" }], []),
  Error,
  "an entry short of a key is rejected",
);
assert.throws(
  () =>
    reportLockChanges(
      [
        { name: "p", version: "1.0", source: "one", needs: [] },
        { name: "p", version: "2.0", source: "one", needs: [] },
      ],
      [],
    ),
  Error,
  "two entries of one record sharing a name are rejected",
);
assert.throws(
  () =>
    reportLockChanges([{ name: "p", version: "1.0+", source: "one", needs: [] }], []),
  Error,
  "an empty build tag is rejected",
);
assert.throws(
  () =>
    reportLockChanges([{ name: "p", version: "1.0+AB", source: "one", needs: [] }], []),
  Error,
  "an upper-case build tag is rejected",
);
assert.throws(
  () =>
    reportLockChanges([{ name: "p", version: "01.0", source: "one", needs: [] }], []),
  Error,
  "a leading nought in a group is rejected",
);
assert.throws(
  () =>
    reportLockChanges([{ name: "p", version: "1.0", source: "", needs: [] }], []),
  Error,
  "an empty source is rejected",
);
assert.throws(
  () =>
    reportLockChanges(
      [{ name: "p", version: "1.0", source: "one", needs: ["a", "a"] }],
      [],
    ),
  Error,
  "an entry naming one need twice is rejected",
);
assert.throws(
  () =>
    reportLockChanges([{ name: "p", version: "1.0", source: "one", needs: "a" }], []),
  Error,
  "needs that are not a list are rejected",
);
console.log("ok");
