import assert from "node:assert/strict";
import { foldMachine } from "./solution.ts";

assert.deepEqual(
  foldMachine({
    alphabet: ["a"],
    states: ["s0", "s1"],
    start: "s0",
    accepting: ["s1"],
    moves: [
      ["s0", "a", "s1"],
      ["s1", "a", "s0"],
    ],
  }),
  {
    size: 2,
    start: 0,
    accepting: [1],
    moves: [
      [0, "a", 1],
      [1, "a", 0],
    ],
  },
  "a machine already at its smallest comes back renumbered"
);

assert.deepEqual(
  foldMachine({
    alphabet: ["a"],
    states: ["p", "q", "r"],
    start: "p",
    accepting: ["q", "r"],
    moves: [
      ["p", "a", "q"],
      ["q", "a", "q"],
      ["r", "a", "r"],
    ],
  }),
  {
    size: 2,
    start: 0,
    accepting: [1],
    moves: [
      [0, "a", 1],
      [1, "a", 1],
    ],
  },
  "a state nothing reaches simply goes"
);

assert.deepEqual(
  foldMachine({
    alphabet: ["a"],
    states: ["x", "y"],
    start: "x",
    accepting: ["y"],
    moves: [
      ["x", "a", "x"],
      ["y", "a", "y"],
    ],
  }),
  { size: 1, start: 0, accepting: [], moves: [[0, "a", 0]] },
  "when the only survivor accepts nothing the accepting list is empty"
);

assert.deepEqual(
  foldMachine({
    alphabet: ["a", "b"],
    states: ["m", "n"],
    start: "m",
    accepting: ["m", "n"],
    moves: [
      ["m", "a", "n"],
      ["m", "b", "m"],
      ["n", "a", "m"],
      ["n", "b", "n"],
    ],
  }),
  {
    size: 1,
    start: 0,
    accepting: [0],
    moves: [
      [0, "a", 0],
      [0, "b", 0],
    ],
  },
  "two states nothing tells apart collapse into one"
);

assert.deepEqual(
  foldMachine({
    alphabet: ["a", "b"],
    states: ["S0", "S1", "S2", "S3"],
    start: "S0",
    accepting: ["S1", "S3"],
    moves: [
      ["S0", "a", "S1"],
      ["S0", "b", "S2"],
      ["S1", "a", "S1"],
      ["S1", "b", "S2"],
      ["S2", "a", "S3"],
      ["S2", "b", "S2"],
      ["S3", "a", "S3"],
      ["S3", "b", "S2"],
    ],
  }),
  {
    size: 2,
    start: 0,
    accepting: [1],
    moves: [
      [0, "a", 1],
      [0, "b", 0],
      [1, "a", 1],
      [1, "b", 0],
    ],
  },
  "four states fold to the two the language really needs"
);

assert.deepEqual(
  foldMachine({
    alphabet: ["a"],
    states: ["q0", "q1", "q2", "q3"],
    start: "q0",
    accepting: ["q3"],
    moves: [
      ["q0", "a", "q1"],
      ["q1", "a", "q2"],
      ["q2", "a", "q3"],
      ["q3", "a", "q3"],
    ],
  }),
  {
    size: 4,
    start: 0,
    accepting: [3],
    moves: [
      [0, "a", 1],
      [1, "a", 2],
      [2, "a", 3],
      [3, "a", 3],
    ],
  },
  "states only a long run tells apart must survive the folding"
);

assert.deepEqual(
  foldMachine({
    alphabet: ["b", "a"],
    states: ["s", "x", "y"],
    start: "s",
    accepting: ["x"],
    moves: [
      ["s", "b", "x"],
      ["s", "a", "y"],
      ["x", "a", "x"],
      ["x", "b", "x"],
      ["y", "a", "y"],
      ["y", "b", "y"],
    ],
  }),
  {
    size: 3,
    start: 0,
    accepting: [1],
    moves: [
      [0, "b", 1],
      [0, "a", 2],
      [1, "b", 1],
      [1, "a", 1],
      [2, "b", 2],
      [2, "a", 2],
    ],
  },
  "numbering and move order follow the alphabet as it was listed"
);

const sound = {
  alphabet: ["a"],
  states: ["s0", "s1"],
  start: "s0",
  accepting: ["s1"],
  moves: [
    ["s0", "a", "s1"],
    ["s1", "a", "s0"],
  ],
};
const bent = (patch) => foldMachine({ ...sound, ...patch });

assert.throws(() => bent({ alphabet: [] }), Error, "an empty alphabet is rejected");
assert.throws(
  () => bent({ alphabet: ["a", "a"] }),
  Error,
  "a repeated symbol is rejected"
);
assert.throws(() => bent({ states: [] }), Error, "an empty state list is rejected");
assert.throws(
  () => bent({ states: ["s0", "s0", "s1"] }),
  Error,
  "a repeated state is rejected"
);
assert.throws(
  () => bent({ start: "nowhere" }),
  Error,
  "a start nobody declared is rejected"
);
assert.throws(
  () => bent({ accepting: ["ghost"] }),
  Error,
  "an accepting name nobody declared is rejected"
);
assert.throws(
  () => bent({ accepting: ["s1", "s1"] }),
  Error,
  "an accepting name listed twice is rejected"
);
assert.throws(
  () => bent({ moves: [["s0", "z", "s1"], ["s1", "a", "s0"]] }),
  Error,
  "a move on an undeclared symbol is rejected"
);
assert.throws(
  () => bent({ moves: [["s0", "a", "s9"], ["s1", "a", "s0"]] }),
  Error,
  "a move onto an undeclared state is rejected"
);
assert.throws(
  () => bent({ moves: [["s0", "a", "s1"]] }),
  Error,
  "a state with no move on a symbol is rejected"
);
assert.throws(
  () =>
    bent({
      moves: [
        ["s0", "a", "s1"],
        ["s0", "a", "s0"],
        ["s1", "a", "s0"],
      ],
    }),
  Error,
  "a state with two moves on one symbol is rejected"
);

console.log("ok");
