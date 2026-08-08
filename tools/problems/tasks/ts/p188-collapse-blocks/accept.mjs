import assert from "node:assert/strict";
import { collapseBlocks } from "./solution.ts";

const berth = (value) => {
  const fields = [];
  let rest = value;
  for (let slot = 0; slot < 4; slot += 1) {
    fields.unshift(rest % 8);
    rest = Math.floor(rest / 8);
  }
  return fields.join(".");
};

assert.deepEqual(collapseBlocks([]), [], "no berths, no slabs");
assert.deepEqual(collapseBlocks(["3.1.4.2"]), ["3.1.4.2/4"], "one berth is a full pin");
assert.deepEqual(
  collapseBlocks(["1.1.1.1", "1.1.1.1"]),
  ["1.1.1.1/4"],
  "a repeated berth counts once",
);
assert.deepEqual(
  collapseBlocks(["7.0.0.0", "0.0.0.1"]),
  ["0.0.0.1/4", "7.0.0.0/4"],
  "slabs come out lowest first",
);

const eight = [];
for (let last = 0; last < 8; last += 1) {
  eight.push("1.2.3." + String(last));
}
assert.deepEqual(collapseBlocks(eight), ["1.2.3.0/3"], "eight siblings fold to one");
assert.deepEqual(
  collapseBlocks(eight.slice(0, 7)),
  eight.slice(0, 7).map((one) => one + "/4"),
  "seven siblings stay written out",
);
assert.deepEqual(
  collapseBlocks([...eight, "5.5.5.5"]),
  ["1.2.3.0/3", "5.5.5.5/4"],
  "a fold and a lone berth together",
);

const sixtyFour = [];
for (let third = 0; third < 8; third += 1) {
  for (let last = 0; last < 8; last += 1) {
    sixtyFour.push("0.0." + String(third) + "." + String(last));
  }
}
assert.deepEqual(
  collapseBlocks(sixtyFour),
  ["0.0.0.0/2"],
  "folding runs twice in a row",
);
assert.deepEqual(
  collapseBlocks(sixtyFour.slice(1)),
  ["0.0.0.1/4", "0.0.0.2/4", "0.0.0.3/4", "0.0.0.4/4", "0.0.0.5/4",
   "0.0.0.6/4", "0.0.0.7/4", "0.0.1.0/3", "0.0.2.0/3", "0.0.3.0/3",
   "0.0.4.0/3", "0.0.5.0/3", "0.0.6.0/3", "0.0.7.0/3"],
  "one berth missing stops only its own group folding",
);

const everything = [];
for (let value = 0; value < 4096; value += 1) {
  everything.push(berth(value));
}
assert.deepEqual(collapseBlocks(everything), ["0.0.0.0/0"], "the whole space folds");
assert.deepEqual(
  collapseBlocks(everything.slice(0, 512)),
  ["0.0.0.0/1"],
  "one eighth of the space folds to a single pin",
);

assert.throws(() => collapseBlocks(["1.2.3"]), Error, "three fields are rejected");
assert.throws(() => collapseBlocks(["1.2.3.4.5"]), Error, "five fields are rejected");
assert.throws(() => collapseBlocks(["1.2.3.8"]), Error, "a field of eight is rejected");
assert.throws(() => collapseBlocks(["1.2.3.a"]), Error, "a letter field is rejected");
assert.throws(() => collapseBlocks(["1.2..3"]), Error, "an empty field is rejected");
assert.throws(() => collapseBlocks(["01.2.3.4"]), Error, "a padded field is rejected");
assert.throws(() => collapseBlocks("1.2.3.4"), Error, "a bare string is rejected");
assert.throws(() => collapseBlocks([17]), Error, "a non-string element is rejected");
console.log("ok");
