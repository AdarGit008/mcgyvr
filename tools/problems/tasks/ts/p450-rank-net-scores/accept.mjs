import assert from "node:assert/strict";
import { rankNetScores } from "./solution.ts";

assert.deepEqual(
  rankNetScores([{ name: "Ada", gross: 90, mark: 12 }]),
  [{ place: 1, name: "Ada", net: 84 }],
  "a mark of twelve earns six",
);

assert.deepEqual(
  rankNetScores([
    { name: "Bry", gross: 85, mark: 4 },
    { name: "Ada", gross: 96, mark: 20 },
    { name: "Cyd", gross: 88, mark: 7 },
  ]),
  [
    { place: 1, name: "Ada", net: 81 },
    { place: 2, name: "Bry", net: 85 },
    { place: 3, name: "Cyd", net: 85 },
  ],
  "level nets are parted by the lower gross",
);

assert.deepEqual(
  rankNetScores([
    { name: "Zed", gross: 90, mark: 0 },
    { name: "Abe", gross: 90, mark: 4 },
  ]),
  [
    { place: 1, name: "Abe", net: 90 },
    { place: 2, name: "Zed", net: 90 },
  ],
  "level on both counts falls back to the name",
);

assert.deepEqual(
  rankNetScores([
    { name: "b0", gross: 100, mark: 5 },
    { name: "b1", gross: 100, mark: 9 },
    { name: "b2", gross: 100, mark: 10 },
    { name: "b3", gross: 100, mark: 14 },
  ]),
  [
    { place: 1, name: "b2", net: 94 },
    { place: 2, name: "b3", net: 94 },
    { place: 3, name: "b0", net: 97 },
    { place: 4, name: "b1", net: 97 },
  ],
  "the edges of two bands earn the same allowance",
);

assert.deepEqual(
  rankNetScores([
    { name: "top", gross: 100, mark: 15 },
    { name: "bot", gross: 100, mark: 28 },
  ]),
  [
    { place: 1, name: "bot", net: 85 },
    { place: 2, name: "top", net: 90 },
  ],
  "the widest band earns fifteen at either edge",
);

assert.deepEqual(
  rankNetScores([{ name: "low", gross: 10, mark: 28 }]),
  [{ place: 1, name: "low", net: -5 }],
  "a net score may fall below zero",
);

assert.throws(() => rankNetScores([]), Error, "an empty field is refused");
assert.throws(() => rankNetScores("field"), Error, "a field that is not a list is refused");
assert.throws(
  () => rankNetScores([{ name: "", gross: 90, mark: 3 }]),
  Error,
  "an empty name is refused",
);
assert.throws(
  () => rankNetScores([{ gross: 90, mark: 3 }]),
  Error,
  "a missing name is refused",
);
assert.throws(
  () => rankNetScores([{ name: "Ada", gross: 90, mark: 3 }, { name: "Ada", gross: 91, mark: 3 }]),
  Error,
  "one name entered twice is refused",
);
assert.throws(
  () => rankNetScores([{ name: "Ada", gross: 0, mark: 3 }]),
  Error,
  "a gross score of zero is refused",
);
assert.throws(
  () => rankNetScores([{ name: "Ada", gross: 90.5, mark: 3 }]),
  Error,
  "a gross score that is not whole is refused",
);
assert.throws(
  () => rankNetScores([{ name: "Ada", gross: 90, mark: 29 }]),
  Error,
  "a mark past the table is refused",
);
assert.throws(
  () => rankNetScores([{ name: "Ada", gross: 90, mark: -1 }]),
  Error,
  "a negative mark is refused",
);
assert.throws(
  () => rankNetScores([{ name: "Ada", gross: 90, mark: "12" }]),
  Error,
  "a mark that is not a number is refused",
);
console.log("ok");
