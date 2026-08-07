import assert from "node:assert/strict";
import { rankSeriesNet } from "./solution.ts";

const bands = [
  { limit: 4, allowance: 0 },
  { limit: 9, allowance: 3 },
  { limit: 19, allowance: 8 },
  { limit: 28, allowance: 15 },
];

const round = (gross, weight) => ({ gross, weight });

const ada = {
  name: "Ada",
  mark: 12,
  rounds: [round(90, 100), round(88, 110), round(95, 90)],
};
const bry = {
  name: "Bry",
  mark: 2,
  rounds: [round(84, 100), round(86, 100), round(83, 100), round(90, 100)],
};
const cyd = {
  name: "Cyd",
  mark: 25,
  rounds: [round(100, 100), round(98, 120), round(102, 80)],
};
const dov = { name: "Dov", mark: 5, rounds: [round(80, 100), round(81, 100)] };
const eli = { name: "Eli", mark: 5, rounds: [] };

assert.deepEqual(
  rankSeriesNet([ada], bands),
  {
    standings: [{ place: 1, name: "Ada", total: 250, counted: [0, 1, 2] }],
    unranked: [],
  },
  "three rounds all count, and each weight is cut down on its own",
);

assert.deepEqual(
  rankSeriesNet([bry], bands),
  {
    standings: [{ place: 1, name: "Bry", total: 253, counted: [0, 1, 2] }],
    unranked: [],
  },
  "a fourth round sets the worst one aside",
);

assert.deepEqual(
  rankSeriesNet([cyd], bands),
  {
    standings: [{ place: 1, name: "Cyd", total: 255, counted: [0, 1, 2] }],
    unranked: [],
  },
  "a weight above one hundred lifts the allowance",
);

assert.deepEqual(
  rankSeriesNet([dov, ada, cyd, eli, bry], bands),
  {
    standings: [
      { place: 1, name: "Ada", total: 250, counted: [0, 1, 2] },
      { place: 2, name: "Bry", total: 253, counted: [0, 1, 2] },
      { place: 3, name: "Cyd", total: 255, counted: [0, 1, 2] },
    ],
    unranked: ["Dov", "Eli"],
  },
  "short entries drop out and the rest are ordered by total",
);

assert.deepEqual(
  rankSeriesNet(
    [
      { name: "Fay", mark: 0, rounds: [round(100, 100), round(100, 100), round(100, 100)] },
      { name: "Gus", mark: 0, rounds: [round(95, 100), round(100, 100), round(105, 100)] },
    ],
    bands,
  ),
  {
    standings: [
      { place: 1, name: "Gus", total: 300, counted: [0, 1, 2] },
      { place: 2, name: "Fay", total: 300, counted: [0, 1, 2] },
    ],
    unranked: [],
  },
  "level totals are parted by the best remaining net",
);

assert.deepEqual(
  rankSeriesNet(
    [
      { name: "Ivo", mark: 0, rounds: [round(100, 100), round(100, 100), round(100, 100)] },
      { name: "Hal", mark: 0, rounds: [round(100, 100), round(100, 100), round(100, 100)] },
    ],
    bands,
  ),
  {
    standings: [
      { place: 1, name: "Hal", total: 300, counted: [0, 1, 2] },
      { place: 2, name: "Ivo", total: 300, counted: [0, 1, 2] },
    ],
    unranked: [],
  },
  "level on every count falls back to the name",
);

assert.deepEqual(
  rankSeriesNet(
    [
      {
        name: "Kip",
        mark: 0,
        rounds: [round(90, 100), round(95, 100), round(95, 100), round(80, 100)],
      },
    ],
    bands,
  ),
  {
    standings: [{ place: 1, name: "Kip", total: 265, counted: [0, 1, 3] }],
    unranked: [],
  },
  "two rounds level at the worst set the later one aside",
);

assert.deepEqual(
  rankSeriesNet(
    [
      {
        name: "Lys",
        mark: 25,
        rounds: [round(100, 33), round(100, 100), round(100, 200)],
      },
    ],
    bands,
  ),
  {
    standings: [{ place: 1, name: "Lys", total: 251, counted: [0, 1, 2] }],
    unranked: [],
  },
  "a weight of thirty three cuts fifteen down to four",
);

assert.deepEqual(
  rankSeriesNet([eli], bands),
  { standings: [], unranked: ["Eli"] },
  "a competitor who played nothing stands nowhere",
);

assert.throws(() => rankSeriesNet([], bands), Error, "no entries is refused");
assert.throws(() => rankSeriesNet("Ada", bands), Error, "entries that are not a list are refused");
assert.throws(() => rankSeriesNet([ada], []), Error, "no bands is refused");
assert.throws(
  () => rankSeriesNet([ada], [{ limit: 9, allowance: 3 }, { limit: 4, allowance: 0 }]),
  Error,
  "band limits that fall are refused",
);
assert.throws(
  () => rankSeriesNet([ada], [{ limit: 4, allowance: 0 }, { limit: 4, allowance: 3 }]),
  Error,
  "two bands sharing a limit are refused",
);
assert.throws(
  () => rankSeriesNet([{ name: "Ada", mark: 30, rounds: ada.rounds }], bands),
  Error,
  "a mark above every band is refused",
);
assert.throws(
  () => rankSeriesNet([{ name: "", mark: 2, rounds: ada.rounds }], bands),
  Error,
  "an empty name is refused",
);
assert.throws(() => rankSeriesNet([ada, ada], bands), Error, "one name entered twice is refused");
assert.throws(
  () => rankSeriesNet([{ name: "Ada", mark: -1, rounds: ada.rounds }], bands),
  Error,
  "a negative mark is refused",
);
assert.throws(
  () => rankSeriesNet([{ name: "Ada", mark: 2, rounds: "three" }], bands),
  Error,
  "rounds that are not a list are refused",
);
assert.throws(
  () => rankSeriesNet([{ name: "Ada", mark: 2, rounds: [round(0, 100)] }], bands),
  Error,
  "a gross score of zero is refused",
);
assert.throws(
  () => rankSeriesNet([{ name: "Ada", mark: 2, rounds: [round(90, 0)] }], bands),
  Error,
  "a weight of zero is refused",
);
assert.throws(
  () => rankSeriesNet([{ name: "Ada", mark: 2, rounds: [round(90, 201)] }], bands),
  Error,
  "a weight above two hundred is refused",
);
assert.throws(
  () => rankSeriesNet([ada], [{ limit: 4, allowance: -1 }]),
  Error,
  "a negative band allowance is refused",
);
console.log("ok");
