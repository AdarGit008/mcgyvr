import assert from "node:assert/strict";
import { judgeVaneTrick } from "./solution.ts";

assert.deepEqual(
  judgeVaneTrick({
    trump: "bare",
    lead: 0,
    holdings: [["5k", "2n"], ["9n", "4k"], ["7k"], ["3k", "8t"]],
    played: ["5k", "9n", "7k", "3k"],
  }),
  { taker: 2, revokes: [1] },
  "a hot card of an idle plume takes nothing",
);
assert.deepEqual(
  judgeVaneTrick({
    trump: "t",
    lead: 2,
    holdings: [["8p"], ["5p", "9k"], ["6p"], ["2t", "4p"]],
    played: ["6p", "2t", "8p", "5p"],
  }),
  { taker: 0, revokes: [3] },
  "a trump laid in renege is set aside",
);
assert.deepEqual(
  judgeVaneTrick({
    trump: "k",
    lead: 0,
    holdings: [["4n", "3t"], ["9t", "5k"], ["2k"], ["6n"]],
    played: ["4n", "9t", "2k", "6n"],
  }),
  { taker: 2, revokes: [] },
  "the coolest trump still beats the hottest plain card",
);
assert.deepEqual(
  judgeVaneTrick({
    trump: "k",
    lead: 0,
    holdings: [["4n"], ["8k", "5n"], ["6n"], ["2n"]],
    played: ["4n", "8k", "6n", "2n"],
  }),
  { taker: 2, revokes: [1] },
  "setting the reneged trump aside hands the trick back to the called plume",
);
assert.deepEqual(
  judgeVaneTrick({
    trump: "n",
    lead: 1,
    holdings: [["2p", "6t"], ["7t"], ["3n", "5t"], ["9t"]],
    played: ["7t", "3n", "9t", "2p"],
  }),
  { taker: 3, revokes: [0, 2] },
  "two seats renege and the seat numbers come out in order",
);
assert.deepEqual(
  judgeVaneTrick({
    trump: "bare",
    lead: 3,
    holdings: [["4p"], ["9p"], ["2p"], ["7p"]],
    played: ["7p", "4p", "9p", "2p"],
  }),
  { taker: 1, revokes: [] },
  "one plume all round with the lead away from seat zero",
);

const sound = {
  trump: "bare",
  lead: 0,
  holdings: [["5k"], ["9n"], ["7k"], ["3k"]],
  played: ["5k", "9n", "7k", "3k"],
};
assert.throws(() => judgeVaneTrick("play"), Error, "a string is not a play");
assert.throws(() => judgeVaneTrick({ ...sound, trump: "z" }), Error, "an unknown trump plume");
assert.throws(() => judgeVaneTrick({ ...sound, lead: 4 }), Error, "a lead outside the table");
assert.throws(
  () => judgeVaneTrick({ ...sound, holdings: [["5k"], ["9n"], ["7k"]] }),
  Error,
  "three holdings are refused",
);
assert.throws(
  () => judgeVaneTrick({ ...sound, holdings: [["5k"], ["9n"], ["7k"], ["3k", "5k"]] }),
  Error,
  "one card in two holdings is refused",
);
assert.throws(
  () => judgeVaneTrick({ ...sound, played: ["5k", "9n", "7k"] }),
  Error,
  "three cards laid are refused",
);
assert.throws(
  () => judgeVaneTrick({ ...sound, played: ["5k", "9n", "7k", "2t"] }),
  Error,
  "a seat cannot lay a card it never held",
);
assert.throws(
  () => judgeVaneTrick({ ...sound, played: ["5k", "9n", "7k", "10k"] }),
  Error,
  "a heat outside 2 to 9 is refused",
);
console.log("ok");
