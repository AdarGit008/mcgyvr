import assert from "node:assert/strict";
import { evaluateRules } from "./solution.ts";

assert.equal(
  evaluateRules([], { role: "guest", door: "lab" }),
  "deny",
  "no rules defaults to deny"
);

assert.equal(
  evaluateRules(
    [
      { effect: "allow", role: "guest", door: "lab" },
      { effect: "deny", role: "everyone", door: "all" },
    ],
    { role: "guest", door: "lab" }
  ),
  "allow",
  "the first matching rule decides, not the last"
);

assert.equal(
  evaluateRules(
    [
      { effect: "deny", role: "guest", door: "all" },
      { effect: "allow", role: "everyone", door: "lab" },
    ],
    { role: "guest", door: "lab" }
  ),
  "deny",
  "a deny first stays a deny"
);

assert.equal(
  evaluateRules(
    [{ effect: "allow", role: "everyone", door: "archive" }],
    { role: "clerk", door: "archive" }
  ),
  "allow",
  "everyone covers any role"
);

assert.equal(
  evaluateRules(
    [{ effect: "allow", role: "clerk", door: "all" }],
    { role: "clerk", door: "roof" }
  ),
  "allow",
  "all covers any door"
);

assert.equal(
  evaluateRules(
    [{ effect: "allow", role: "clerk", door: "roof" }],
    { role: "guest", door: "roof" }
  ),
  "deny",
  "a role mismatch falls through to deny"
);

assert.equal(
  evaluateRules(
    [
      { effect: "deny", role: "everyone", door: "vault" },
      { effect: "allow", role: "manager", door: "vault" },
    ],
    { role: "manager", door: "vault" }
  ),
  "deny",
  "an earlier broad deny shadows a later allow"
);

console.log("ok");
