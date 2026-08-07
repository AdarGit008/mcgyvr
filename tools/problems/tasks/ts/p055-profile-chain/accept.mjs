import assert from "node:assert/strict";
import { resolveProfile } from "./solution.ts";

assert.deepEqual(
  resolveProfile({ base: { x: 1, y: 2 } }, "base"),
  { x: 1, y: 2 },
  "a chainless profile resolves to its own settings",
);
assert.deepEqual(
  resolveProfile(
    { base: { x: 1, y: 2 }, dev: { extends: "base", y: 3 } },
    "dev",
  ),
  { x: 1, y: 3 },
  "a descendant setting beats its ancestor",
);
assert.deepEqual(
  resolveProfile(
    {
      base: { retries: 1, log: "warn" },
      staging: { extends: "base", log: "info" },
      local: { extends: "staging", debug: true },
    },
    "local",
  ),
  { retries: 1, log: "info", debug: true },
  "three-level chains fold root-first",
);
assert.deepEqual(
  resolveProfile(
    { base: { x: 1 }, dev: { extends: "base" } },
    "base",
  ),
  { x: 1 },
  "resolving an ancestor ignores its descendants",
);
const untouched = { base: { x: 1 }, dev: { extends: "base", y: 2 } };
resolveProfile(untouched, "dev");
assert.deepEqual(
  untouched,
  { base: { x: 1 }, dev: { extends: "base", y: 2 } },
  "the input must not be mutated",
);
assert.throws(
  () => resolveProfile({ base: { x: 1 } }, "prod"),
  Error,
  "an unknown requested name is rejected",
);
assert.throws(
  () => resolveProfile({ dev: { extends: "ghost" } }, "dev"),
  Error,
  "an extends target with no profile is rejected",
);
assert.throws(
  () =>
    resolveProfile(
      { a: { extends: "b" }, b: { extends: "a" } },
      "a",
    ),
  Error,
  "a two-profile cycle is rejected",
);
assert.throws(
  () => resolveProfile({ a: { extends: "a" } }, "a"),
  Error,
  "a self-extending profile is rejected",
);
console.log("ok");
