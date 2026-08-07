import assert from "node:assert/strict";
import { apportionLegCosts } from "./solution.ts";

const route = [
  { name: "quito", cents: 1000, payer: "ana" },
  { name: "cusco", cents: 1001, payer: "bo" },
  { name: "lima", cents: 7, payer: "cy" },
];
const party = [
  { name: "ana", joins: "quito", leaves: "lima" },
  { name: "bo", joins: "quito", leaves: "cusco" },
  { name: "cy", joins: "cusco", leaves: "lima" },
];

assert.deepEqual(
  apportionLegCosts(route, party),
  [
    { name: "ana", owes: 838, paid: 1000 },
    { name: "bo", owes: 834, paid: 1001 },
    { name: "cy", owes: 336, paid: 7 },
  ],
  "shares follow who was aboard, leftovers going by ascending name",
);

const shares = apportionLegCosts(route, party);
assert.equal(
  shares.reduce((sum, row) => sum + row.owes, 0),
  2008,
  "the carried shares add up to the whole trip",
);
assert.equal(
  shares.reduce((sum, row) => sum + row.paid, 0),
  2008,
  "what was handed over adds up to the whole trip",
);

assert.deepEqual(
  apportionLegCosts(
    [{ name: "hop", cents: 5, payer: "solo" }],
    [{ name: "solo", joins: "hop", leaves: "hop" }],
  ),
  [{ name: "solo", owes: 5, paid: 5 }],
  "a lone traveller carries the whole leg",
);

assert.deepEqual(
  apportionLegCosts(
    [{ name: "hop", cents: 0, payer: "zoe" }],
    [
      { name: "zoe", joins: "hop", leaves: "hop" },
      { name: "abe", joins: "hop", leaves: "hop" },
    ],
  ),
  [
    { name: "abe", owes: 0, paid: 0 },
    { name: "zoe", owes: 0, paid: 0 },
  ],
  "a leg that cost nothing leaves nobody carrying anything",
);

assert.deepEqual(
  apportionLegCosts(
    [{ name: "hop", cents: 10, payer: "dee" }],
    [
      { name: "dee", joins: "hop", leaves: "hop" },
      { name: "cal", joins: "hop", leaves: "hop" },
      { name: "bex", joins: "hop", leaves: "hop" },
    ],
  ),
  [
    { name: "bex", owes: 4, paid: 0 },
    { name: "cal", owes: 3, paid: 0 },
    { name: "dee", owes: 3, paid: 10 },
  ],
  "the single leftover cent goes to the first name alphabetically",
);

assert.deepEqual(
  apportionLegCosts(
    [
      { name: "one", cents: 100, payer: "gus" },
      { name: "two", cents: 100, payer: "gus" },
    ],
    [
      { name: "gus", joins: "one", leaves: "one" },
      { name: "hal", joins: "two", leaves: "two" },
    ],
  ),
  [
    { name: "gus", owes: 100, paid: 200 },
    { name: "hal", owes: 100, paid: 0 },
  ],
  "the one who paid a leg need not have ridden it",
);

assert.throws(() => apportionLegCosts([], party), Error, "a trip with no legs");
assert.throws(
  () => apportionLegCosts(route, []),
  Error,
  "a trip with no travellers",
);
assert.throws(
  () =>
    apportionLegCosts(
      [{ name: "hop", cents: 5, payer: "ghost" }],
      [{ name: "solo", joins: "hop", leaves: "hop" }],
    ),
  Error,
  "a payer the party does not list is rejected",
);
assert.throws(
  () =>
    apportionLegCosts(
      [{ name: "hop", cents: 5, payer: "solo" }],
      [{ name: "solo", joins: "hop", leaves: "elsewhere" }],
    ),
  Error,
  "leaving at a leg the trip does not run is rejected",
);
assert.throws(
  () =>
    apportionLegCosts(
      [
        { name: "one", cents: 5, payer: "solo" },
        { name: "two", cents: 5, payer: "solo" },
      ],
      [{ name: "solo", joins: "two", leaves: "one" }],
    ),
  Error,
  "leaving before joining is rejected",
);
assert.throws(
  () =>
    apportionLegCosts(
      [
        { name: "one", cents: 5, payer: "solo" },
        { name: "two", cents: 5, payer: "solo" },
      ],
      [{ name: "solo", joins: "one", leaves: "one" }],
    ),
  Error,
  "a leg nobody rode is rejected",
);
assert.throws(
  () =>
    apportionLegCosts(
      [{ name: "hop", cents: -5, payer: "solo" }],
      [{ name: "solo", joins: "hop", leaves: "hop" }],
    ),
  Error,
  "a leg costing less than nothing is rejected",
);
assert.throws(
  () =>
    apportionLegCosts(
      [{ name: "hop", cents: 5, payer: "solo", tip: 1 }],
      [{ name: "solo", joins: "hop", leaves: "hop" }],
    ),
  Error,
  "a leg with a spare key is rejected",
);
assert.throws(
  () =>
    apportionLegCosts(
      [{ name: "hop", cents: 5, payer: "solo" }],
      [
        { name: "solo", joins: "hop", leaves: "hop" },
        { name: "solo", joins: "hop", leaves: "hop" },
      ],
    ),
  Error,
  "two travellers sharing a name are rejected",
);
console.log("ok");
