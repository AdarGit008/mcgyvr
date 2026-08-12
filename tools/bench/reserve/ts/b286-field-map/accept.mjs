import assert from "node:assert/strict";
import { fieldMap } from "./solution.ts";

assert.deepEqual(fieldMap(["a=1", "b=2"]), { a: "1", b: "2" }, "two settings");
assert.deepEqual(fieldMap(["a=1", "a=2"]), { a: "2" }, "the later one wins");
assert.deepEqual(fieldMap(["plain"]), {}, "no equals sign, skipped");
assert.deepEqual(fieldMap([]), {}, "nothing to read");
assert.deepEqual(
  fieldMap(["url=http://x?y=z"]),
  { url: "http://x?y=z" },
  "only the first equals separates",
);
assert.deepEqual(fieldMap(["a="]), { a: "" }, "an empty value is still a value");
console.log("ok");
