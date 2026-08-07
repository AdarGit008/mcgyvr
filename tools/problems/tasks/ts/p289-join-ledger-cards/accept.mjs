import assert from "node:assert/strict";
import { joinLedgerCards } from "./solution.ts";

const layout = [
  { name: "who", start: 1, width: 6 },
  { name: "what", start: 7, width: 8 },
];

assert.deepEqual(
  joinLedgerCards(["=Ann...Tools..."], layout),
  [{ who: "Ann", what: "Tools" }],
  "one opening card, packing removed from the right",
);
assert.deepEqual(
  joinLedgerCards(["=..x...Y......."], layout),
  [{ who: "..x", what: "Y" }],
  "full stops that lead a value belong to it",
);
assert.deepEqual(
  joinLedgerCards(["=Ann...Tools...", "+bury..&nails.."], layout),
  [{ who: "Annbury", what: "Tools&nails" }],
  "a carrying card lengthens the open record",
);
assert.deepEqual(
  joinLedgerCards(
    ["=Ann...Tools...", "+bury..&nails..", "+..st..&wax...."],
    layout,
  ),
  [{ who: "Annbury..st", what: "Tools&nails&wax" }],
  "two carrying cards in succession",
);
assert.deepEqual(
  joinLedgerCards(["=Bo....Rope....", "+.............."], layout),
  [{ who: "Bo", what: "Rope" }],
  "a card of nothing but packing adds nothing",
);
assert.deepEqual(
  joinLedgerCards(
    ["=Ann...Tools...", "+bury..&nails..", "=Bo....Rope....", "=..x...Y......."],
    layout,
  ),
  [
    { who: "Annbury", what: "Tools&nails" },
    { who: "Bo", what: "Rope" },
    { who: "..x", what: "Y" },
  ],
  "one record per opening card, in the order opened",
);
assert.deepEqual(
  joinLedgerCards(["=Bo....Rope....spare columns"], layout),
  [{ who: "Bo", what: "Rope" }],
  "columns beyond the layout are left alone",
);
assert.deepEqual(
  joinLedgerCards(["=..done"], [{ name: "solo", start: 3, width: 4 }]),
  [{ solo: "done" }],
  "a layout may start part way into the body",
);

assert.throws(() => joinLedgerCards(["=abcdef"], []), Error, "an empty layout");
assert.throws(() => joinLedgerCards([], layout), Error, "no cards at all");
assert.throws(
  () => joinLedgerCards(["+Ann...Tools..."], layout),
  Error,
  "a first card that carries",
);
assert.throws(
  () => joinLedgerCards(["-Ann...Tools..."], layout),
  Error,
  "an unknown marker",
);
assert.throws(() => joinLedgerCards(["=Ann"], layout), Error, "a body cut short");
assert.throws(
  () =>
    joinLedgerCards(["=abcdefgh"], [
      { name: "a", start: 1, width: 4 },
      { name: "a", start: 5, width: 2 },
    ]),
  Error,
  "repeated field name",
);
assert.throws(
  () =>
    joinLedgerCards(["=abcdefgh"], [
      { name: "a", start: 1, width: 4 },
      { name: "b", start: 4, width: 2 },
    ]),
  Error,
  "two fields over one column",
);
assert.throws(
  () => joinLedgerCards(["=abcdefgh"], [{ name: "a", start: 0, width: 2 }]),
  Error,
  "a start left of the body",
);
assert.throws(() => joinLedgerCards([9], layout), Error, "a card that is not a string");
console.log("ok");
