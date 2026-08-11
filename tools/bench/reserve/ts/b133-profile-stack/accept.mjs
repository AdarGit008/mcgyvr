import assert from "node:assert/strict";
import { mergeLayers, resolveProfile } from "./solution.ts";

assert.deepEqual(
  mergeLayers({ a: 1, sub: { x: 1, y: 2 } }, { sub: { y: 3 }, b: 4 }),
  { a: 1, sub: { x: 1, y: 3 }, b: 4 },
  "nested mappings merge key by key",
);
assert.deepEqual(mergeLayers({ k: 1 }, { k: { deep: 2 } }), { k: { deep: 2 } }, "a mapping replaces a scalar");
assert.deepEqual(mergeLayers({ k: { deep: 2 } }, { k: 0 }), { k: 0 }, "a scalar replaces a mapping");
const pristine = { keep: { safe: 1 } };
mergeLayers(pristine, { keep: { safe: 2 } });
assert.deepEqual(pristine, { keep: { safe: 1 } }, "the base is never mutated");
assert.throws(() => mergeLayers(5, {}), Error, "non-mapping base is rejected");

assert.deepEqual(
  resolveProfile("solo", { solo: { settings: { tone: "calm" } } }),
  { tone: "calm" },
  "a profile with no parents is its own settings",
);
assert.deepEqual(resolveProfile("bare", { bare: {} }), {}, "no settings resolves empty");
const catalog = {
  base: { settings: { net: { host: "hub.local", port: 90 }, retries: 2 } },
  edge: { extends: ["base"], settings: { net: { port: 9090 } } },
};
assert.deepEqual(
  resolveProfile("edge", catalog),
  { net: { host: "hub.local", port: 9090 }, retries: 2 },
  "a child deep-overrides its parent",
);
const pair = {
  left: { settings: { mode: "dry", size: 1 } },
  right: { settings: { mode: "wet" } },
  both: { extends: ["left", "right"] },
};
assert.deepEqual(resolveProfile("both", pair), { mode: "wet", size: 1 }, "a later parent wins");
const chain = {
  root: { settings: { depth: 0, tag: "r" } },
  mid: { extends: ["root"], settings: { depth: 1 } },
  leaf: { extends: ["mid"], settings: { tip: true } },
};
assert.deepEqual(
  resolveProfile("leaf", chain),
  { depth: 1, tag: "r", tip: true },
  "a chain resolves through every ancestor",
);
const diamond = {
  core: { settings: { seed: 1, side: "none" } },
  west: { extends: ["core"], settings: { side: "w" } },
  east: { extends: ["core"], settings: { side: "e" } },
  rim: { extends: ["west", "east"] },
};
assert.deepEqual(resolveProfile("rim", diamond), { seed: 1, side: "e" }, "a diamond is not a cycle");
assert.throws(() => resolveProfile("ghost", {}), Error, "unknown profile is rejected");
assert.throws(() => resolveProfile("a", { a: { extends: ["b"] } }), Error, "unknown parent is rejected");
assert.throws(() => resolveProfile("a", { a: { extends: ["a"] } }), Error, "self cycle is rejected");
assert.throws(
  () => resolveProfile("a", { a: { extends: ["b"] }, b: { extends: ["a"] } }),
  Error,
  "mutual cycle is rejected",
);
assert.throws(() => resolveProfile("a", { a: { extends: "b" } }), Error, "non-list extends is rejected");
assert.throws(() => resolveProfile("a", { a: { extends: [5] } }), Error, "non-string parent is rejected");
assert.throws(() => resolveProfile("a", { a: { settings: 3 } }), Error, "non-mapping settings is rejected");
assert.throws(() => resolveProfile("a", { a: "nope" }), Error, "non-mapping profile is rejected");
console.log("ok");
