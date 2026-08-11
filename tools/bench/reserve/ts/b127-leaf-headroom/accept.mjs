import assert from "node:assert/strict";
import { leafHeadroom } from "./solution.ts";

assert.deepEqual(
  leafHeadroom({ limit: 100, children: { api: { limit: 40, used: 15 } } }),
  { api: 25 },
  "the leaf's own limit binds",
);
assert.deepEqual(
  leafHeadroom({ limit: 30, children: { api: { limit: 40, used: 5 } } }),
  { api: 25 },
  "the root's limit binds",
);
assert.deepEqual(
  leafHeadroom({
    limit: 100,
    children: { a: { limit: 60, used: 20 }, b: { limit: 80, used: 50 } },
  }),
  { a: 30, b: 30 },
  "a sibling's burn counts against the shared root",
);
assert.deepEqual(
  leafHeadroom({
    limit: 50,
    children: { team: { limit: 30, children: { job: { limit: 20, used: 5 } } } },
  }),
  { "team/job": 15 },
  "nested groups join the path with a slash",
);
assert.deepEqual(
  leafHeadroom({ limit: 10, children: { a: { limit: 8, used: 9 } } }),
  { a: 0 },
  "an overspent leaf floors at zero",
);
assert.deepEqual(
  leafHeadroom({ limit: 5, children: {} }),
  {},
  "a childless root yields no leaves",
);
assert.deepEqual(
  leafHeadroom({
    limit: 20,
    children: { idle: { limit: 5, children: {} }, live: { limit: 6, used: 2 } },
  }),
  { live: 4 },
  "an empty subgroup contributes no leaves",
);
assert.deepEqual(
  leafHeadroom({
    limit: 90,
    children: {
      org: {
        limit: 60,
        children: { app: { limit: 40, children: { key: { limit: 12, used: 2 } } } },
      },
    },
  }),
  { "org/app/key": 10 },
  "a deep path names every enclosing group",
);
assert.throws(() => leafHeadroom("nope"), Error, "a non-object root is rejected");
assert.throws(() => leafHeadroom({ limit: 5, used: 1 }), Error, "a leaf root is rejected");
assert.throws(() => leafHeadroom({ children: {} }), Error, "a missing limit is rejected");
assert.throws(() => leafHeadroom({ limit: -5, children: {} }), Error, "a negative limit is rejected");
assert.throws(
  () => leafHeadroom({ limit: 10, used: 3, children: {} }),
  Error,
  "a group carrying used is rejected",
);
assert.throws(
  () => leafHeadroom({ limit: 10, children: "many" }),
  Error,
  "non-mapping children are rejected",
);
assert.throws(
  () => leafHeadroom({ limit: 10, children: { a: { limit: 5 } } }),
  Error,
  "a leaf without used is rejected",
);
assert.throws(
  () => leafHeadroom({ limit: 10, children: { a: { limit: 5, used: -1 } } }),
  Error,
  "negative used is rejected",
);
assert.throws(
  () => leafHeadroom({ limit: 10, children: { "": { limit: 5, used: 0 } } }),
  Error,
  "an empty child name is rejected",
);
assert.throws(
  () => leafHeadroom({ limit: 10, children: { "a/b": { limit: 5, used: 0 } } }),
  Error,
  "a slash in a child name is rejected",
);
console.log("ok");
