import assert from "node:assert/strict";
import { firstBareWatch } from "./solution.ts";

const duty = [
  ["helm", "lookout", "helm"],
  ["helm", "lookout"],
  ["lookout"],
];

assert.equal(
  firstBareWatch(duty, [["lookout", "1"]]),
  0,
  "one lookout stands every watch",
);
assert.equal(
  firstBareWatch(duty, [
    ["helm", "1"],
    ["lookout", "1"],
  ]),
  3,
  "the last watch has nobody at the helm",
);
assert.equal(
  firstBareWatch(duty, [["helm", "2"]]),
  2,
  "the second watch musters only one helm",
);
assert.equal(
  firstBareWatch(duty, [["cook", "1"]]),
  1,
  "no watch carries a cook at all",
);
assert.equal(
  firstBareWatch([[]], [["helm", "1"]]),
  1,
  "a watch with nobody standing is bare",
);
assert.equal(
  firstBareWatch([["helm"]], [["helm", "1"]]),
  0,
  "a single hand answers a single demand",
);
assert.equal(
  firstBareWatch(
    [
      ["helm", "helm", "helm"],
      ["helm", "helm", "helm"],
    ],
    [["helm", "3"]],
  ),
  0,
  "three hands on each of two watches",
);
assert.throws(
  () => firstBareWatch([], [["helm", "1"]]),
  Error,
  "a day with no watches is rejected",
);
assert.throws(
  () => firstBareWatch("helm", [["helm", "1"]]),
  Error,
  "a string is not a duty list",
);
assert.throws(
  () => firstBareWatch(["helm"], [["helm", "1"]]),
  Error,
  "a watch entry that is not a list is rejected",
);
assert.throws(
  () => firstBareWatch([["helm", ""]], [["helm", "1"]]),
  Error,
  "a blank warrant name is rejected",
);
assert.throws(
  () => firstBareWatch(duty, []),
  Error,
  "a standing order with nothing in it is rejected",
);
assert.throws(
  () => firstBareWatch(duty, [["helm"]]),
  Error,
  "a standing order row that is not a pair is rejected",
);
assert.throws(
  () => firstBareWatch(duty, [["helm", "two"]]),
  Error,
  "a lettered headcount is rejected",
);
assert.throws(
  () => firstBareWatch(duty, [["helm", "0"]]),
  Error,
  "a headcount of nought is rejected",
);
assert.throws(
  () =>
    firstBareWatch(duty, [
      ["helm", "1"],
      ["helm", "2"],
    ]),
  Error,
  "one warrant demanded twice is rejected",
);
console.log("ok");
