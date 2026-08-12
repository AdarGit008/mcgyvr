import assert from "node:assert/strict";
import { installOrder } from "./solution.ts";

assert.deepEqual(
  installOrder(["c", "a", "b"], []),
  ["a", "b", "c"],
  "no requirements installs alphabetically",
);
assert.deepEqual(
  installOrder(["app", "lib", "core"], [["app", "lib"], ["lib", "core"]]),
  ["core", "lib", "app"],
  "a chain follows its requirements",
);
assert.deepEqual(
  installOrder(["d", "b", "a", "c"], [["d", "a"], ["c", "a"]]),
  ["a", "b", "c", "d"],
  "ties break alphabetically mid-run",
);
assert.deepEqual(
  installOrder(
    ["top", "left", "right", "base"],
    [["top", "left"], ["top", "right"], ["left", "base"], ["right", "base"]],
  ),
  ["base", "left", "right", "top"],
  "a diamond resolves bottom-up",
);
assert.deepEqual(
  installOrder(
    ["mail", "auth", "db", "ui"],
    [["mail", "auth"], ["ui", "auth"], ["mail", "db"]],
  ),
  ["auth", "db", "mail", "ui"],
  "independent branches interleave alphabetically",
);
assert.deepEqual(installOrder(["solo"], []), ["solo"], "a single package");
assert.deepEqual(
  installOrder(["a", "b"], [["b", "a"], ["b", "a"]]),
  ["a", "b"],
  "a repeated requirement pair is harmless",
);
assert.throws(() => installOrder(["pkg", "pkg"], []), Error, "duplicate name");
assert.throws(
  () => installOrder(["a", "b"], [["a", "ghost"]]),
  Error,
  "unknown package in a pair",
);
assert.throws(() => installOrder(["a"], [["a", "a"]]), Error, "self-cycle");
assert.throws(
  () => installOrder(["a", "b"], [["a", "b"], ["b", "a"]]),
  Error,
  "two-package cycle",
);
assert.throws(
  () => installOrder(["a", "b", "c"], [["b", "a"], ["c", "b"], ["b", "c"]]),
  Error,
  "a cycle behind a valid head is still rejected",
);
console.log("ok");
