import assert from "node:assert/strict";
import { resolveAccess } from "./solution.ts";

assert.deepEqual(
  resolveAccess([], { action: "read", path: ["docs"] }),
  { decision: "deny", rule: -1 },
  "no rules means default deny"
);

assert.deepEqual(
  resolveAccess(
    [
      { effect: "allow", action: "read", path: [] },
      { effect: "deny", action: "read", path: ["vault"] },
    ],
    { action: "read", path: ["vault", "keys"] }
  ),
  { decision: "deny", rule: 1 },
  "longer path prefix wins over the catch-all"
);

assert.deepEqual(
  resolveAccess(
    [
      { effect: "deny", action: "any", path: ["docs"] },
      { effect: "allow", action: "read", path: ["docs"] },
    ],
    { action: "read", path: ["docs"] }
  ),
  { decision: "allow", rule: 1 },
  "exact action beats the any action at equal path length"
);

assert.deepEqual(
  resolveAccess(
    [
      { effect: "allow", action: "write", path: ["a"] },
      { effect: "deny", action: "write", path: ["a"] },
    ],
    { action: "write", path: ["a", "b"] }
  ),
  { decision: "deny", rule: 1 },
  "deny beats allow when fully tied"
);

assert.deepEqual(
  resolveAccess(
    [
      { effect: "allow", action: "read", path: ["x"] },
      { effect: "allow", action: "read", path: ["x"] },
    ],
    { action: "read", path: ["x"] }
  ),
  { decision: "allow", rule: 0 },
  "earlier rule wins between identical rules"
);

assert.deepEqual(
  resolveAccess(
    [{ effect: "allow", action: "read", path: ["a", "b"] }],
    { action: "read", path: ["a"] }
  ),
  { decision: "deny", rule: -1 },
  "a rule path longer than the request is not a prefix"
);

assert.deepEqual(
  resolveAccess(
    [{ effect: "allow", action: "write", path: ["a"] }],
    { action: "read", path: ["a"] }
  ),
  { decision: "deny", rule: -1 },
  "action mismatch means no match"
);

assert.throws(
  () =>
    resolveAccess(
      [{ effect: "block", action: "read", path: [] }],
      { action: "read", path: [] }
    ),
  Error,
  "unknown effect is rejected"
);

assert.throws(
  () =>
    resolveAccess(
      [{ effect: "allow", action: "", path: [] }],
      { action: "read", path: [] }
    ),
  Error,
  "empty rule action is rejected"
);

console.log("ok");
