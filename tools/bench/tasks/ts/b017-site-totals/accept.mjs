import assert from "node:assert/strict";
import { loadLedger, siteTotals, busiestSite } from "./solution.ts";

const row = (site, item, qty) => ({ site, item, qty });

assert.deepEqual(siteTotals([]), [], "no rows means no totals");
assert.deepEqual(
  siteTotals([row("east", "pump", 5)]),
  [["east", 5]],
  "a single row is its own total",
);
assert.deepEqual(
  siteTotals([row("east", "pump", 3), row("west", "valve", 2), row("east", "hose", 4)]),
  [["east", 7], ["west", 2]],
  "a repeated site accumulates across its rows",
);
assert.deepEqual(
  siteTotals([row("west", "valve", 2), row("east", "pump", 3)]),
  [["east", 3], ["west", 2]],
  "totals come back sorted by site name",
);
assert.deepEqual(
  siteTotals([
    row("north", "pipe", 4),
    row("south", "clamp", 1),
    row("north", "pipe", 6),
    row("east", "pump", 2),
    row("south", "clamp", 3),
  ]),
  [["east", 2], ["north", 10], ["south", 4]],
  "several sites with several repeats each",
);
assert.deepEqual(
  siteTotals([row("mid", "bolt", 1), row("mid", "bolt", 2), row("mid", "bolt", 3)]),
  [["mid", 6]],
  "one site across three rows sums all three",
);
assert.throws(() => siteTotals([row("east", "pump", 0)]), Error, "zero qty");
assert.throws(() => siteTotals([row("east", "pump", -3)]), Error, "negative qty");
assert.throws(() => siteTotals([row("east", "pump", 2.5)]), Error, "fractional qty");
assert.throws(() => siteTotals([row("east", "pump", true)]), Error, "boolean qty");
assert.equal(
  busiestSite([row("north", "pipe", 4), row("south", "clamp", 9), row("east", "pump", 2)]),
  "south",
  "the largest total wins",
);
assert.equal(
  busiestSite([row("west", "valve", 5), row("east", "pump", 5)]),
  "east",
  "a total tie goes to the alphabetically first site",
);
assert.equal(busiestSite([]), null, "an empty ledger has no busiest site");
assert.deepEqual(
  loadLedger(["east,pump,5", "west,valve,2"]),
  [row("east", "pump", 5), row("west", "valve", 2)],
  "loadLedger parses well-formed lines",
);
assert.throws(() => loadLedger(["east,pump"]), Error, "a two-field line is rejected");
console.log("ok");
