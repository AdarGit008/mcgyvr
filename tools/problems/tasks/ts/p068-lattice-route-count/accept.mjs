import assert from "node:assert/strict";
import { latticeRouteCount } from "./solution.ts";

assert.equal(latticeRouteCount([[0, 0], [0, 0]], ), 2, "open 2x2 has two routes");
assert.equal(
  latticeRouteCount([[0, 0, 0], [0, 0, 0], [0, 0, 0]]),
  6,
  "open 3x3 has six routes",
);
assert.equal(
  latticeRouteCount([[0, 1, 0], [0, 0, 0]]),
  1,
  "cells past a first-row obstacle are not entry points",
);
assert.equal(
  latticeRouteCount([[0, 1, 0]]),
  0,
  "a blocked single row cannot be crossed",
);
assert.equal(
  latticeRouteCount([[0], [1], [0]]),
  0,
  "a blocked single column cannot be descended",
);
assert.equal(
  latticeRouteCount([[0, 0, 0], [0, 1, 0], [0, 0, 0]]),
  2,
  "a centre obstacle leaves the two rim routes",
);
assert.equal(latticeRouteCount([[0]]), 1, "a single clear cell counts one route");
assert.equal(
  latticeRouteCount([[0, 0, 0, 0], [0, 1, 1, 0], [0, 0, 0, 0]]),
  2,
  "a wall in the middle row",
);
assert.equal(latticeRouteCount([[1, 0], [0, 0]]), 0, "a marked start counts nothing");
assert.throws(() => latticeRouteCount([[0, 0], [0]]), Error, "ragged grid rejected");
assert.throws(() => latticeRouteCount([[0, 5]]), Error, "bad cell rejected");
assert.throws(() => latticeRouteCount([]), Error, "empty grid rejected");
console.log("ok");
