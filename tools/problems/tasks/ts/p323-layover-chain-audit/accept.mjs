import assert from "node:assert/strict";
import { checkLayovers } from "./solution.ts";

const pair = [
  { ref: "h1", board: "K", alight: "L", leaves: 60, lands: 90 },
  { ref: "h2", board: "L", alight: "M", leaves: 105, lands: 140 },
];

assert.deepEqual(
  checkLayovers(pair, 15, 0),
  { verdict: "sound", at: -1, arrive: 140 },
  "a wait of exactly the layover is enough",
);
assert.deepEqual(
  checkLayovers(pair, 16, 0),
  { verdict: "tight", at: 1, arrive: -1 },
  "one minute more than the wait allows faults the second hop",
);
assert.deepEqual(
  checkLayovers(pair, 15, 60),
  { verdict: "sound", at: -1, arrive: 140 },
  "leaving exactly at readyAt is not early",
);
assert.deepEqual(
  checkLayovers(pair, 15, 61),
  { verdict: "early", at: 0, arrive: -1 },
  "the opening hop leaves before the traveller is ready",
);

const wrongHalt = [
  { ref: "h1", board: "K", alight: "L", leaves: 60, lands: 90 },
  { ref: "h2", board: "N", alight: "M", leaves: 95, lands: 140 },
];
assert.deepEqual(
  checkLayovers(wrongHalt, 15, 0),
  { verdict: "place", at: 1, arrive: -1 },
  "a hop faulted both ways is faulted as place",
);
assert.deepEqual(
  checkLayovers(wrongHalt, 0, 0),
  { verdict: "place", at: 1, arrive: -1 },
  "the halt still fails when no wait is demanded",
);

const single = [{ ref: "h1", board: "K", alight: "L", leaves: 60, lands: 90 }];
assert.deepEqual(
  checkLayovers(single, 99, 0),
  { verdict: "sound", at: -1, arrive: 90 },
  "a lone hop has no change to audit",
);
assert.deepEqual(
  checkLayovers(single, 99, 61),
  { verdict: "early", at: 0, arrive: -1 },
  "a lone hop can still be early",
);

const triple = [
  { ref: "h1", board: "K", alight: "L", leaves: 60, lands: 90 },
  { ref: "h2", board: "L", alight: "M", leaves: 105, lands: 140 },
  { ref: "h3", board: "M", alight: "P", leaves: 150, lands: 175 },
];
assert.deepEqual(
  checkLayovers(triple, 10, 0),
  { verdict: "sound", at: -1, arrive: 175 },
  "three hops with exact waits throughout",
);
assert.deepEqual(
  checkLayovers(triple, 11, 0),
  { verdict: "tight", at: 2, arrive: -1 },
  "the third hop is the first to fault",
);

assert.throws(() => checkLayovers([], 5, 0), Error, "an empty chain is rejected");
assert.throws(() => checkLayovers("chain", 5, 0), Error, "a non-list chain is rejected");
assert.throws(
  () => checkLayovers([{ ref: "h1", board: "K", alight: "L", leaves: 60 }], 5, 0),
  Error,
  "a hop missing lands is rejected",
);
assert.throws(
  () => checkLayovers([{ ref: "h1", board: "K", alight: "K", leaves: 60, lands: 90 }], 5, 0),
  Error,
  "boarding and alighting at one halt is rejected",
);
assert.throws(
  () => checkLayovers([{ ref: "h1", board: "K", alight: "L", leaves: 90, lands: 90 }], 5, 0),
  Error,
  "landing no later than leaving is rejected",
);
assert.throws(
  () => checkLayovers([{ ref: "", board: "K", alight: "L", leaves: 60, lands: 90 }], 5, 0),
  Error,
  "an empty ref is rejected",
);
assert.throws(() => checkLayovers(pair, -1, 0), Error, "a negative layover is rejected");
assert.throws(() => checkLayovers(pair, 5, 2.5), Error, "a fractional readyAt is rejected");
console.log("ok");
