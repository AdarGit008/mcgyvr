import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { groupByLength } from "./solution.ts";

const grouped = groupByLength(["a", "bb", "cc", "d"]);
assert.ok(grouped instanceof Map, "returns a Map");
assert.deepEqual(grouped.get(1), ["a", "d"], "one-character words");
assert.deepEqual(grouped.get(2), ["bb", "cc"], "two-character words");
assert.deepEqual([...grouped.keys()], [1, 2], "keys in first-seen order");
assert.equal(groupByLength([]).size, 0, "empty input");
assert.deepEqual(groupByLength([""]).get(0), [""], "the empty string has length zero");

const source = readFileSync(new URL("./solution.ts", import.meta.url), "utf8");
assert.ok(
  /words\s*:\s*readonly\s+string\[\]/.test(source),
  "the parameter must be annotated `readonly string[]`",
);
assert.ok(
  /:\s*Map<\s*number\s*,\s*string\[\]\s*>/.test(source),
  "the return must be annotated `Map<number, string[]>`",
);
assert.ok(
  !/Array<\s*string\s*>/.test(source),
  "use the modern `string[]` form, not `Array<string>`",
);
