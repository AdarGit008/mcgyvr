import assert from "node:assert/strict";
import { agedServiceOrder } from "./solution.ts";

const join = (tick, who, rank) => ({ kind: "join", tick, who, rank });
const call = (tick) => ({ kind: "call", tick });

assert.deepEqual(
  agedServiceOrder([join(0, "a", 1), join(0, "b", 3), call(1)], 5),
  ["b"],
  "with no aging yet the higher rank goes first"
);

assert.deepEqual(
  agedServiceOrder([join(0, "old", 1), join(9, "new", 2), call(10)], 5),
  ["old"],
  "two aging steps lift the long waiter past a fresher caller"
);

assert.deepEqual(
  agedServiceOrder([join(0, "old", 1), join(4, "new", 2), call(4)], 5),
  ["new"],
  "before a whole step passes the rank still decides"
);

assert.deepEqual(
  agedServiceOrder([join(0, "alpha", 0), join(5, "beta", 1), call(5)], 5),
  ["alpha"],
  "level standing goes to the earlier join tick"
);

assert.deepEqual(
  agedServiceOrder([join(0, "zeta", 2), join(0, "beta", 2), call(0)], 5),
  ["beta"],
  "level standing and equal join ticks go to the earlier name"
);

assert.deepEqual(
  agedServiceOrder(
    [join(0, "p", 0), join(0, "q", 4), join(1, "r", 2), call(1), call(7), call(7)],
    3
  ),
  ["q", "r", "p"],
  "standings are recomputed at every call"
);

assert.deepEqual(
  agedServiceOrder(
    [join(0, "a", 1), call(0), join(1, "b", 0), join(2, "c", 0), call(9), call(9)],
    4
  ),
  ["a", "b", "c"],
  "callers joining after a call age from their own join tick"
);

assert.deepEqual(
  agedServiceOrder([join(0, "x", 1), call(0), join(1, "x", 1), call(1)], 5),
  ["x", "x"],
  "a name freed by a call may join again"
);

assert.throws(
  () => agedServiceOrder([join(0, "a", 1), call(0)], 0),
  Error,
  "a step of zero is rejected"
);
assert.throws(() => agedServiceOrder([], 5), Error, "an empty log is rejected");
assert.throws(
  () => agedServiceOrder([{ kind: "leave", tick: 0 }], 5),
  Error,
  "an unknown kind is rejected"
);
assert.throws(
  () => agedServiceOrder([join(-1, "a", 1)], 5),
  Error,
  "a negative tick is rejected"
);
assert.throws(
  () => agedServiceOrder([join(5, "a", 1), call(2)], 5),
  Error,
  "a tick running backwards is rejected"
);
assert.throws(
  () => agedServiceOrder([join(0, "", 1)], 5),
  Error,
  "a joining caller with no name is rejected"
);
assert.throws(
  () => agedServiceOrder([join(0, "a", -1)], 5),
  Error,
  "a negative rank is rejected"
);
assert.throws(
  () => agedServiceOrder([join(0, "a", 1), join(1, "a", 2)], 5),
  Error,
  "a name already waiting cannot join again"
);
assert.throws(
  () => agedServiceOrder([call(0)], 5),
  Error,
  "a call on an empty waiting room is rejected"
);

console.log("ok");
