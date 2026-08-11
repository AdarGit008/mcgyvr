import assert from "node:assert/strict";
import { expandMarkers } from "./solution.ts";

assert.equal(expandMarkers("all clear", {}), "all clear", "no markers passes through");
assert.equal(expandMarkers("gate %gate% open", { gate: "B4" }), "gate B4 open", "single marker");
assert.equal(
  expandMarkers("%a%-%b%-%a%", { a: "x", b: "y" }),
  "x-y-x",
  "a repeated marker expands each time",
);
assert.equal(
  expandMarkers("%left%%right%", { left: "L", right: "R" }),
  "LR",
  "adjacent markers both expand",
);
assert.equal(expandMarkers("100%% done", {}), "100% done", "doubled percent is literal");
assert.equal(
  expandMarkers("%pct%%% full", { pct: "75" }),
  "75% full",
  "a marker then a literal percent",
);
assert.equal(expandMarkers("", {}), "", "empty template stays empty");
assert.throws(() => expandMarkers(9, {}), Error, "non-string template is rejected");
assert.throws(() => expandMarkers("%who%", {}), Error, "unknown marker is rejected");
assert.throws(() => expandMarkers("%a b%", { "a b": "x" }), Error, "malformed name is rejected");
assert.throws(() => expandMarkers("half %done", { done: "d" }), Error, "unclosed marker is rejected");
assert.throws(() => expandMarkers("%n%", { n: 3 }), Error, "non-string value is rejected");
console.log("ok");
