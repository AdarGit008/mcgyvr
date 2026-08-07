import assert from "node:assert/strict";
import { firstSkillGap } from "./solution.ts";

const roster = [
  ["ivy", "540", "780", "till", "keys"],
  ["rex", "600", "900", "till"],
];

assert.equal(
  firstSkillGap(roster, [["till", "1", "540", "900"]]),
  "covered",
  "one till hand is on duty right across the demand",
);
assert.equal(
  firstSkillGap(roster, [["keys", "1", "540", "900"]]),
  "780-900 keys",
  "the only key holder goes home before the demand closes",
);
assert.equal(
  firstSkillGap(roster, [["till", "2", "540", "900"]]),
  "540-600 till",
  "the second till hand has not arrived yet",
);
assert.equal(
  firstSkillGap(roster, [["till", "2", "600", "780"]]),
  "covered",
  "a demand narrowed to the busy stretch is met",
);
assert.equal(
  firstSkillGap(roster, [
    ["keys", "1", "540", "900"],
    ["till", "2", "540", "900"],
  ]),
  "540-600 till",
  "the earliest stretch wins over the earliest demand",
);
assert.equal(
  firstSkillGap(roster, [
    ["spare", "1", "780", "900"],
    ["keys", "1", "780", "900"],
  ]),
  "780-900 spare",
  "within one stretch the demands are read in the order handed over",
);
assert.equal(
  firstSkillGap(roster, [["till", "1", "0", "300"]]),
  "0-300 till",
  "an hour nobody is rostered for is a gap",
);
assert.equal(
  firstSkillGap(
    [
      ["ivy", "540", "600", "till"],
      ["rex", "660", "720", "till"],
    ],
    [["till", "1", "540", "720"]],
  ),
  "600-660 till",
  "the hole between two tours is named",
);
assert.equal(
  firstSkillGap([], [["till", "1", "540", "900"]]),
  "540-900 till",
  "an empty roster leaves the whole demand bare",
);
assert.equal(
  firstSkillGap(
    [["ivy", "0", "1440", "till", "keys", "safe"]],
    [
      ["till", "1", "0", "1440"],
      ["safe", "1", "0", "1440"],
    ],
  ),
  "covered",
  "one person covering the whole day answers every demand",
);
assert.throws(
  () => firstSkillGap("ivy", [["till", "1", "0", "60"]]),
  Error,
  "a string is not a roster",
);
assert.throws(
  () => firstSkillGap([["ivy", "540", "780"]], [["till", "1", "0", "60"]]),
  Error,
  "a tour with no skills is rejected",
);
assert.throws(
  () => firstSkillGap([["ivy", "54x", "780", "till"]], [["till", "1", "0", "60"]]),
  Error,
  "a lettered minute is rejected",
);
assert.throws(
  () => firstSkillGap([["ivy", "780", "540", "till"]], [["till", "1", "0", "60"]]),
  Error,
  "a tour that ends before it starts is rejected",
);
assert.throws(
  () => firstSkillGap([["ivy", "540", "1500", "till"]], [["till", "1", "0", "60"]]),
  Error,
  "a minute past 1440 is rejected",
);
assert.throws(
  () =>
    firstSkillGap([["ivy", "540", "780", "till", "till"]], [["till", "1", "0", "60"]]),
  Error,
  "one skill written twice in a tour is rejected",
);
assert.throws(
  () =>
    firstSkillGap(
      [
        ["ivy", "540", "780", "till"],
        ["ivy", "600", "900", "keys"],
      ],
      [["till", "1", "0", "60"]],
    ),
  Error,
  "the same name rostered twice is rejected",
);
assert.throws(
  () => firstSkillGap(roster, []),
  Error,
  "a demand list with nothing in it is rejected",
);
assert.throws(
  () => firstSkillGap(roster, [["till", "1", "540"]]),
  Error,
  "a demand of three fields is rejected",
);
assert.throws(
  () => firstSkillGap(roster, [["till", "0", "540", "900"]]),
  Error,
  "a demand for nobody is rejected",
);
assert.throws(
  () => firstSkillGap(roster, [["till", "1", "900", "540"]]),
  Error,
  "a demand that closes before it opens is rejected",
);
console.log("ok");
