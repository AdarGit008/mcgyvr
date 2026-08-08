import assert from "node:assert/strict";
import { layerConfigs } from "./solution.ts";

assert.deepEqual(
  layerConfigs([{ a: 1 }, { a: 2, b: 3 }]),
  { a: 2, b: 3 },
  "later scalars override earlier ones",
);
assert.deepEqual(
  layerConfigs([{ server: { host: "x", port: 1 } }, { server: { port: 2 } }]),
  { server: { host: "x", port: 2 } },
  "nested mappings merge, preserving siblings",
);
assert.deepEqual(
  layerConfigs([{ a: 1, b: 2 }, { a: null }]),
  { b: 2 },
  "null deletes a key",
);
assert.deepEqual(
  layerConfigs([{ b: 1 }, { a: null }]),
  { b: 1 },
  "deleting an absent key is silent",
);
assert.deepEqual(
  layerConfigs([{ tags: [1, 2] }, { tags: [3] }]),
  { tags: [3] },
  "arrays replace wholesale, never concatenate",
);
assert.deepEqual(
  layerConfigs([{ a: { x: 1 } }, { a: 5 }]),
  { a: 5 },
  "a scalar replaces a mapping wholesale",
);
assert.deepEqual(
  layerConfigs([{ a: 5 }, { a: { x: 1 } }]),
  { a: { x: 1 } },
  "a mapping replaces a scalar wholesale",
);
assert.deepEqual(
  layerConfigs([{ a: { x: 1, y: 2 } }, { a: { x: null } }]),
  { a: { y: 2 } },
  "null deletes inside a nested merge",
);
assert.deepEqual(
  layerConfigs([{ a: 1 }, { a: null }, { a: { x: 2 } }]),
  { a: { x: 2 } },
  "a deleted key may be reintroduced later",
);
assert.deepEqual(layerConfigs([]), {}, "no layers yield an empty result");
const pristine = { server: { port: 1 } };
layerConfigs([pristine, { server: { port: 9 } }]);
assert.deepEqual(
  pristine,
  { server: { port: 1 } },
  "layers must not be mutated",
);
assert.throws(() => layerConfigs("nope"), Error, "non-list argument rejected");
assert.throws(() => layerConfigs([[1, 2]]), Error, "array layer rejected");
assert.throws(() => layerConfigs([null]), Error, "null layer rejected");
console.log("ok");
