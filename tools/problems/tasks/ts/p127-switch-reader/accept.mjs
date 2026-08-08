import assert from "node:assert/strict";
import { readSwitches } from "./solution.ts";

const KINDS = { force: "switch", level: "value" };

assert.deepEqual(
  readSwitches(KINDS, ["--force", "a"]),
  { found: { force: true }, extra: ["a"] },
  "switch records true, bare token passes through",
);
assert.deepEqual(
  readSwitches(KINDS, ["--level", "3"]),
  { found: { level: "3" }, extra: [] },
  "value option takes the next token",
);
assert.deepEqual(
  readSwitches(KINDS, ["--level=a=b"]),
  { found: { level: "a=b" }, extra: [] },
  "split on the first = only",
);
assert.deepEqual(
  readSwitches(KINDS, ["--level", "1", "--level=2"]),
  { found: { level: "2" }, extra: [] },
  "the later recording stands",
);
assert.deepEqual(
  readSwitches(KINDS, ["x", "--force", "y"]),
  { found: { force: true }, extra: ["x", "y"] },
  "extras keep their order",
);
assert.deepEqual(
  readSwitches(KINDS, ["--level=", "z"]),
  { found: { level: "" }, extra: ["z"] },
  "inline empty text is recorded",
);
assert.throws(() => readSwitches(KINDS, ["--wat"]), Error, "unknown name errors");
assert.throws(
  () => readSwitches(KINDS, ["--level"]),
  Error,
  "dangling value option errors",
);
assert.throws(
  () => readSwitches(KINDS, ["--force=on"]),
  Error,
  "switch with inline form errors",
);
console.log("ok");
