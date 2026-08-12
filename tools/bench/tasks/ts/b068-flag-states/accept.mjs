import assert from "node:assert/strict";
import { flagStates } from "./solution.ts";

assert.deepEqual(
  flagStates(5, ["read", "write", "exec"]),
  { read: true, write: false, exec: true },
  "mixed bits",
);
assert.deepEqual(flagStates(0, ["trace", "color"]), { trace: false, color: false }, "zero mask clears every flag");
assert.deepEqual(
  flagStates(7, ["read", "write", "exec"]),
  { read: true, write: true, exec: true },
  "saturated mask",
);
assert.deepEqual(flagStates(1, ["armed"]), { armed: true }, "single-flag catalog");
assert.throws(() => flagStates(-3, ["dryrun"]), Error, "negative mask is rejected");
assert.throws(() => flagStates(0, []), Error, "empty catalog is rejected");
assert.throws(() => flagStates(1, ["", "quiet"]), Error, "empty flag name is rejected");
assert.throws(() => flagStates(1, ["quiet", "quiet"]), Error, "repeated flag name is rejected");
assert.throws(() => flagStates(4, ["quiet", "loud"]), Error, "bit beyond the catalog is rejected");
console.log("ok");
