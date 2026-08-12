import assert from "node:assert/strict";
import { routeHops } from "./solution.ts";

assert.equal(routeHops([], "hub", "hub"), 0, "staying put costs zero links");
assert.equal(routeHops([["north", "mill"]], "mill", "north"), 1, "a link is ridden backwards too");
assert.equal(
  routeHops([["a", "b"], ["b", "c"], ["c", "a"]], "a", "c"),
  1,
  "a ring does not trap the search",
);
assert.equal(
  routeHops([["a", "b"], ["b", "d"], ["a", "c"], ["c", "e"], ["e", "d"]], "a", "d"),
  2,
  "the shorter of two routes wins",
);
assert.equal(routeHops([["a", "b"], ["c", "d"]], "a", "d"), -1, "an unreachable goal is -1");
assert.throws(() => routeHops([], "", "hub"), Error, "an empty origin is rejected");
assert.throws(() => routeHops([], "hub", 7), Error, "a non-string goal is rejected");
assert.throws(() => routeHops([["a", "b", "c"]], "a", "b"), Error, "a three-station link is rejected");
assert.throws(() => routeHops([["a", ""]], "a", "b"), Error, "an unnamed link station is rejected");
console.log("ok");
