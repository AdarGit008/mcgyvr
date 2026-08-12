import assert from "node:assert/strict";
import { reachableModes } from "./solution.ts";

const panel = {
  idle: { power: "warming", diag: "service" },
  warming: { ready: "printing" },
  printing: { done: "idle", jam: "fault" },
  fault: { clear: "idle" },
  service: { done: "idle", eject: "sleep" },
  offline: { power: "idle" },
  locked: {},
};

assert.deepEqual(reachableModes(panel, "idle"), ["fault", "idle", "printing", "service", "sleep", "warming"], "signals chain onward and a resting mode counts");
assert.deepEqual(reachableModes(panel, "offline"), ["fault", "idle", "offline", "printing", "service", "sleep", "warming"], "an entry mode reaches the whole panel");
assert.deepEqual(reachableModes(panel, "locked"), ["locked"], "a mode answering no signal reaches only itself");
assert.deepEqual(reachableModes({ armed: { fire: "armed" } }, "armed"), ["armed"], "a signal leading back to its own mode settles");
assert.throws(() => reachableModes(["idle"], "idle"), Error, "a table that is not a mapping is rejected");
assert.throws(() => reachableModes(panel, "sleep"), Error, "a starting mode the table does not key is rejected");
console.log("ok");
