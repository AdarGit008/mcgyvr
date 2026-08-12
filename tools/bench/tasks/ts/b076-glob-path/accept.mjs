import assert from "node:assert/strict";
import { globPath } from "./solution.ts";

assert.equal(globPath("b?g/*.txt", "bag/note.txt"), true, "wildcards match inside their segments");
assert.equal(globPath("src/*.ts", "src/lib/main.ts"), false, "star stops at a slash");
assert.equal(globPath("a?b", "a/b"), false, "question mark refuses a slash");
assert.equal(globPath("rel*", "rel"), true, "star may match nothing");
assert.equal(globPath("notes.txt", "notes.md"), false, "literals must match exactly");
assert.throws(() => globPath(7, "a"), Error, "non-string pattern is rejected");
assert.throws(() => globPath("a", 7), Error, "non-string path is rejected");
assert.throws(() => globPath("", "a"), Error, "empty pattern is rejected");
assert.throws(() => globPath("a", ""), Error, "empty path is rejected");
console.log("ok");
