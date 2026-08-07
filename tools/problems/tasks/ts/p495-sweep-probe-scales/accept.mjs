import assert from "node:assert/strict";
import { sweepProbeScales } from "./solution.ts";

const deck = (channel, ladder, bias) => ({ channel, ladder, bias });
const took = (channel, count) => ({ channel, count });

assert.deepEqual(
  sweepProbeScales(
    [
      deck("heat", [[0, 0], [100, 1000]], 0),
      deck("cold", [[-50, 20], [50, -20]], 5),
    ],
    [
      took("heat", 50),
      took("heat", -10),
      took("heat", 250),
      took("cold", 0),
      took("cold", 25),
      took("heat", 3),
    ],
  ),
  {
    readings: ["heat 500", "heat 0", "heat 1000", "cold 5", "cold -5", "heat 30"],
    low: 1,
    high: 1,
    span: ["heat 0 1000", "cold -5 5"],
  },
  "two channels, both pins, and a bias on a falling ladder",
);

assert.deepEqual(
  sweepProbeScales(
    [deck("tilt", [[0, 0], [3, 1]], 0)],
    [took("tilt", 1), took("tilt", 2)],
  ),
  { readings: ["tilt 0", "tilt 1"], low: 0, high: 0, span: ["tilt 0 1"] },
  "a third settles down and two thirds settles up",
);

assert.deepEqual(
  sweepProbeScales(
    [deck("up", [[0, 0], [2, 1]], 0), deck("down", [[0, 0], [2, -1]], 0)],
    [took("up", 1), took("down", 1)],
  ),
  {
    readings: ["up 1", "down -1"],
    low: 0,
    high: 0,
    span: ["up 1 1", "down -1 -1"],
  },
  "a half settles away from nought on either side",
);

assert.deepEqual(
  sweepProbeScales(
    [deck("idle", [[0, 5], [10, 5]], 0), deck("busy", [[0, 0], [10, 100]], -3)],
    [took("busy", 5)],
  ),
  { readings: ["busy 47"], low: 0, high: 0, span: ["busy 47 47"] },
  "a channel no sample named is left out of the span",
);

assert.deepEqual(
  sweepProbeScales([deck("pin", [[2, 7], [8, 7]], -7)], [took("pin", 0), took("pin", 99)]),
  { readings: ["pin 0", "pin 0"], low: 1, high: 1, span: ["pin 0 0"] },
  "the bias applies to a pinned figure too",
);

assert.deepEqual(
  sweepProbeScales([deck("edge", [[4, 9], [12, 21]], 0)], [took("edge", 4), took("edge", 12)]),
  { readings: ["edge 9", "edge 21"], low: 0, high: 0, span: ["edge 9 21"] },
  "a count sitting exactly on an end rung is no pin at all",
);

assert.deepEqual(
  sweepProbeScales([deck("quiet", [[0, 0], [5, 5]], 0)], []),
  { readings: [], low: 0, high: 0, span: [] },
  "no samples leaves every tally at nought",
);

assert.deepEqual(
  sweepProbeScales(
    [deck("bend", [[0, 0], [4, 40], [10, 10]], 0)],
    [took("bend", 2), took("bend", 7)],
  ),
  { readings: ["bend 20", "bend 25"], low: 0, high: 0, span: ["bend 20 25"] },
  "the rising rung and the falling rung are told apart",
);

assert.throws(() => sweepProbeScales("no", []), Error, "channels must be a list");
assert.throws(() => sweepProbeScales([4], []), Error, "a channel must be a record");
assert.throws(
  () => sweepProbeScales([{ channel: "a", ladder: [[0, 0], [1, 1]] }], []),
  Error,
  "a missing channel key is refused",
);
assert.throws(
  () => sweepProbeScales([deck("", [[0, 0], [1, 1]], 0)], []),
  Error,
  "an empty channel name is refused",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[0, 0], [1, 1]], 0), deck("a", [[0, 0], [2, 2]], 0)], []),
  Error,
  "a repeated channel name is refused",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[0, 0]], 0)], []),
  Error,
  "a one-rung ladder is refused",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[0, 0], [1, 1, 1]], 0)], []),
  Error,
  "a three-entry rung is refused",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[0, 0], [1, "x"]], 0)], []),
  Error,
  "a non-numeric rung entry is refused",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[5, 0], [5, 1]], 0)], []),
  Error,
  "repeated tick figures are refused",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[0, 0], [1, 1]], 1.5)], []),
  Error,
  "a fractional bias is refused",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[0, 0], [1, 1]], 0)], "no"),
  Error,
  "samples must be a list",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[0, 0], [1, 1]], 0)], [{ channel: "a" }]),
  Error,
  "a missing sample key is refused",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[0, 0], [1, 1]], 0)], [took("b", 0)]),
  Error,
  "an undeclared channel is refused",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[0, 0], [1, 1]], 0)], [took("a", 0.5)]),
  Error,
  "a fractional count is refused",
);
assert.throws(
  () => sweepProbeScales([deck("a", [[0, 0], [1, 1]], 0)], [took("a", 5000000)]),
  Error,
  "a count beyond a million is refused",
);
console.log("ok");
