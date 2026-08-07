import assert from "node:assert/strict";
import { summariseLockDiff } from "./solution.ts";

const before = {
  alpha: "1.9",
  bravo: "2.0.0",
  delta: "0.1",
  echo: "1.2",
  foxtrot: "3.4.5",
  hotel: "5.0",
  india: "1.0.0",
};
const after = {
  bravo: "2.0.0",
  charlie: "0.0.1",
  delta: "0.0.9",
  echo: "1.2.0",
  alpha: "1.10",
  zulu: "1.0",
  golf: "2.2",
  hotel: "4.9.9",
  india: "1.0.1",
};

assert.deepEqual(
  summariseLockDiff(before, after),
  {
    added: ["charlie", "golf", "zulu"],
    dropped: ["foxtrot"],
    lifted: ["alpha", "india"],
    lowered: ["delta", "hotel"],
  },
  "the four buckets, each sorted, over a record that moved every way at once",
);

assert.deepEqual(
  summariseLockDiff({}, {}),
  { added: [], dropped: [], lifted: [], lowered: [] },
  "two empty records differ in nothing",
);

assert.deepEqual(
  summariseLockDiff({ pkg: "1" }, { pkg: "1.0.0" }),
  { added: [], dropped: [], lifted: [], lowered: [] },
  "trailing noughts do not make a new release",
);

assert.deepEqual(
  summariseLockDiff({ pkg: "1.9" }, { pkg: "1.10" }),
  { added: [], dropped: [], lifted: ["pkg"], lowered: [] },
  "groups rank as numbers, not as text",
);

assert.deepEqual(
  summariseLockDiff({ pkg: "1.10" }, { pkg: "1.9" }),
  { added: [], dropped: [], lifted: [], lowered: ["pkg"] },
  "the same comparison read the other way round",
);

assert.deepEqual(
  summariseLockDiff({ pkg: "0.0.0" }, { pkg: "0.0.1" }),
  { added: [], dropped: [], lifted: ["pkg"], lowered: [] },
  "a lone nought is a legal group",
);

assert.deepEqual(
  summariseLockDiff({ zeta: "1.0", alfa: "1.0" }, {}),
  { added: [], dropped: ["alfa", "zeta"], lifted: [], lowered: [] },
  "the dropped list is sorted too",
);

assert.deepEqual(
  summariseLockDiff({ pkg: "2.0.0.1" }, { pkg: "2.0.0.0" }),
  { added: [], dropped: [], lifted: [], lowered: ["pkg"] },
  "a fourth group ranks like any other",
);

assert.throws(
  () => summariseLockDiff("nope", {}),
  Error,
  "a record that is not a mapping is rejected",
);
assert.throws(
  () => summariseLockDiff({ pkg: "01.2" }, {}),
  Error,
  "a leading nought in a group is rejected",
);
assert.throws(
  () => summariseLockDiff({ pkg: "" }, {}),
  Error,
  "an empty release is rejected",
);
assert.throws(
  () => summariseLockDiff({ pkg: "1.2." }, {}),
  Error,
  "a trailing full stop is rejected",
);
assert.throws(
  () => summariseLockDiff({ pkg: "1.2-beta" }, {}),
  Error,
  "anything but digits and full stops is rejected",
);
assert.throws(
  () => summariseLockDiff({ pkg: 12 }, {}),
  Error,
  "a release that is not a string is rejected",
);
assert.throws(
  () => summariseLockDiff({ "": "1.0" }, {}),
  Error,
  "an empty package name is rejected",
);
console.log("ok");
