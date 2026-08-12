import assert from "node:assert/strict";
import { rowKey, indexRows } from "./solution.ts";

assert.equal(rowKey("ann"), "A", "a lower-case name is raised");
assert.equal(rowKey("Bob"), "B", "an upper-case name is already right");
assert.deepEqual(
  indexRows(["ann", "amy", "bob"]),
  { A: ["ann", "amy"], B: ["bob"] },
  "two groups in arrival order",
);
assert.deepEqual(indexRows([]), {}, "no names, no index");
assert.deepEqual(
  indexRows(["Ann", "ann"]),
  { A: ["Ann", "ann"] },
  "case does not split a group",
);
assert.deepEqual(indexRows(["zoe"]), { Z: ["zoe"] }, "one name, one group");
console.log("ok");
