import assert from "node:assert/strict";
import { resolveFettleTricks } from "./solution.ts";

assert.deepEqual(
  resolveFettleTricks({ trump: "f", tricks: [["b5", "b13", "f2", "b1"], ["c3", "c1", "c7", "b2"]] }),
  { takers: [2, 3], worths: [9, 8], even: 9, odd: 8 },
  "a lone trump takes the trick and the winner leads the next",
);
assert.deepEqual(
  resolveFettleTricks({ trump: "none", tricks: [["l4", "l9", "c13", "b1"]] }),
  { takers: [1], worths: [12], even: 0, odd: 12 },
  "with no trump only the called house can take",
);
assert.deepEqual(
  resolveFettleTricks({ trump: "b", tricks: [["b13", "b1", "c2", "f3"]] }),
  { takers: [1], worths: [12], even: 0, odd: 12 },
  "a 1 outranks a 13 in the same house",
);
assert.deepEqual(
  resolveFettleTricks({
    trump: "l",
    tricks: [["c4", "c11", "c12", "c6"], ["c10", "l3", "f13", "b1"], ["f4", "f5", "f6", "f7"]],
  }),
  { takers: [2, 3, 2], worths: [5, 10, 3], even: 8, odd: 10 },
  "the leader rotates and the last trick carries the extra three",
);
assert.deepEqual(
  resolveFettleTricks({ trump: "none", tricks: [["b2", "c3", "f4", "l5"]] }),
  { takers: [0], worths: [3], even: 3, odd: 0 },
  "a trick of four houses goes to the seat that called it",
);
assert.deepEqual(
  resolveFettleTricks({ trump: "c", tricks: [["f8", "f12", "c1", "c13"]] }),
  { takers: [2], worths: [15], even: 15, odd: 0 },
  "the strongest trump beats a weaker trump laid after it",
);

assert.throws(() => resolveFettleTricks([]), Error, "a list is not a deal");
assert.throws(
  () => resolveFettleTricks({ trump: "x", tricks: [["b1", "b2", "b3", "b4"]] }),
  Error,
  "an unknown trump house is refused",
);
assert.throws(() => resolveFettleTricks({ trump: "b", tricks: [] }), Error, "an empty deal is refused");
assert.throws(
  () => resolveFettleTricks({ trump: "b", tricks: [["b1", "b2", "b3"]] }),
  Error,
  "a trick of three cards is refused",
);
assert.throws(
  () => resolveFettleTricks({ trump: "b", tricks: [["b01", "b2", "b3", "b4"]] }),
  Error,
  "a padding zero is refused",
);
assert.throws(
  () => resolveFettleTricks({ trump: "b", tricks: [["b14", "b2", "b3", "b4"]] }),
  Error,
  "a strength above 13 is refused",
);
assert.throws(
  () => resolveFettleTricks({ trump: "b", tricks: [["b1", "b2", "b3", "b4"], ["b5", "b6", "b7", "b1"]] }),
  Error,
  "a card laid twice in the deal is refused",
);
console.log("ok");
