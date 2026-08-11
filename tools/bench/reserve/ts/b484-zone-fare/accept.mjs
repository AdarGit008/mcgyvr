import assert from "node:assert/strict";
import { zoneFare } from "./solution.ts";

assert.equal(zoneFare(["central", "market"]), 200, "two stops sharing one zone");
assert.equal(zoneFare(["central", "harbour"]), 400, "two zones touched");
assert.equal(zoneFare(["central", "harbour", "far"]), 600, "three zones touched");
assert.equal(zoneFare(["central"]), 200, "a single stop");
assert.equal(zoneFare(["far", "other"]), 200, "unnamed stops share the outer zone");
assert.equal(zoneFare([]), 0, "a journey calling nowhere");
console.log("ok");
