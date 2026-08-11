import assert from "node:assert/strict";
import { routeStops, routeHops } from "./solution.ts";

assert.deepEqual(routeStops("A>B>C"), ["A", "B", "C"], "three stops");
assert.deepEqual(routeStops(" A > B "), ["A", "B"], "spaces are trimmed");
assert.deepEqual(routeStops("A"), ["A"], "a route of one stop");
assert.deepEqual(routeStops("   "), [], "a blank route has no stops");
assert.equal(routeHops("A>B>C"), 2, "one fewer than the stops");
assert.equal(routeHops("A"), 0, "a single stop is no journey");
assert.equal(routeHops(""), 0, "an empty route");
console.log("ok");
