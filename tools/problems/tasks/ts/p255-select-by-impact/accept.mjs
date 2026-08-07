import assert from "node:assert/strict";
import { selectByImpact } from "./solution.ts";

const graph = {
  core: [],
  util: ["core"],
  parser: ["util"],
  render: ["util", "core"],
  cli: ["parser", "render"],
  docs: [],
};
const suites = {
  "core-unit": ["core"],
  "parse-unit": ["parser"],
  "render-unit": ["render"],
  "cli-e2e": ["cli"],
  "docs-lint": ["docs"],
  smoke: ["docs", "cli"],
};

assert.deepEqual(selectByImpact(graph, suites, []), [], "no edits run nothing");
assert.deepEqual(
  selectByImpact(graph, suites, ["docs"]),
  ["docs-lint", "smoke"],
  "a leaf module disturbs only its own drivers",
);
assert.deepEqual(
  selectByImpact(graph, suites, ["parser"]),
  ["cli-e2e", "parse-unit", "smoke"],
  "disturbance climbs one level to cli and stops",
);
assert.deepEqual(
  selectByImpact(graph, suites, ["core"]),
  ["ALL"],
  "five of six suites trips the override",
);
assert.deepEqual(
  selectByImpact(graph, suites, ["core", "docs"]),
  ["ALL"],
  "every suite running is still the override",
);
assert.deepEqual(
  selectByImpact(graph, suites, ["util", "util"]),
  ["ALL"],
  "a repeated edit is the same edit",
);

const looped = { alpha: ["beta"], beta: ["alpha"], tool: ["alpha"], leaf: [] };
const loopSuites = {
  "loop-a": ["alpha"],
  "loop-b": ["beta"],
  tooly: ["tool"],
  leafy: ["leaf"],
  "spare-x": ["leaf"],
  "spare-y": ["leaf"],
};
assert.deepEqual(
  selectByImpact(looped, loopSuites, ["alpha"]),
  ["loop-a", "loop-b", "tooly"],
  "a two-module cycle terminates and drags in its importer",
);
assert.deepEqual(
  selectByImpact(looped, loopSuites, ["leaf"]),
  ["leafy", "spare-x", "spare-y"],
  "exactly half is not more than half",
);
assert.deepEqual(
  selectByImpact(looped, loopSuites, ["tool"]),
  ["tooly"],
  "nothing imports tool so nothing climbs",
);
assert.deepEqual(selectByImpact({}, {}, []), [], "an empty world runs nothing");

assert.throws(() => selectByImpact(graph, suites, ["ghost"]), Error, "an undeclared edit is rejected");
assert.throws(
  () => selectByImpact({ a: ["b"] }, {}, []),
  Error,
  "an import of an undeclared module is rejected",
);
assert.throws(
  () => selectByImpact({ a: [] }, { s: ["b"] }, []),
  Error,
  "a suite driving an undeclared module is rejected",
);
assert.throws(() => selectByImpact({ a: ["a"] }, {}, []), Error, "a self-import is rejected");
assert.throws(
  () => selectByImpact({ a: ["b", "b"], b: [] }, {}, []),
  Error,
  "a repeated import is rejected",
);
assert.throws(() => selectByImpact({ a: [] }, { "": ["a"] }, []), Error, "an empty suite name is rejected");
assert.throws(() => selectByImpact(graph, suites, "core"), Error, "a string edit list is rejected");
assert.throws(() => selectByImpact([], suites, []), Error, "a list module graph is rejected");
console.log("ok");
