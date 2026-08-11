import assert from "node:assert/strict";
import { maskFault } from "./solution.ts";

assert.equal(maskFault("report-*.log"), "ok", "wildcards and a literal dash are sound");
assert.equal(maskFault("[a-z][0-9]?.txt"), "ok", "two closed classes with rising ranges are sound");
assert.equal(maskFault("draft\\[1\\].txt"), "ok", "an escaped bracket opens no class");
assert.equal(maskFault("trail\\"), "dangling escape at 5", "a trailing backslash is met at its own index");
assert.equal(maskFault("size[0-9"), "unclosed class at 4", "an unclosed class is named at its bracket");
assert.equal(maskFault("[z-a].log"), "reversed range at 1", "a range ending below its start is named at the start");
assert.equal(maskFault("[9-1]x\\"), "reversed range at 1", "the class closes before the trailing backslash is met");
console.log("ok");
