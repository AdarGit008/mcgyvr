import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { activeEmails } from "./solution.ts";

const users = [
  { email: "Ann@Example.com", active: true },
  { email: "bob@example.com", active: false },
  { email: "CAT@EXAMPLE.COM", active: true },
];
assert.deepEqual(
  activeEmails(users),
  ["ann@example.com", "cat@example.com"],
  "active addresses, lowercased, in order",
);
assert.deepEqual(activeEmails([]), [], "empty input");
assert.deepEqual(
  activeEmails([{ email: "x@y.z", active: false }]),
  [],
  "nobody active",
);
assert.deepEqual(
  activeEmails([{ email: "A@B.C", active: true }]),
  ["a@b.c"],
  "single active user",
);

const snapshot = JSON.stringify(users);
activeEmails(users);
assert.equal(JSON.stringify(users), snapshot, "the argument must not be mutated");

// The contract bans both constructs by name; this is what it meant.
const source = readFileSync(new URL("./solution.ts", import.meta.url), "utf8");
assert.ok(!/\bfor\b/.test(source), "the rewritten file must contain no `for` keyword");
assert.ok(!/\.push\b/.test(source), "the rewritten file must not call .push");
