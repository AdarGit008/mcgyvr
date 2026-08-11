import assert from "node:assert/strict";
import { tidyPath } from "./solution.ts";

assert.equal(tidyPath("notes/april"), "notes/april", "a plain path is unchanged");
assert.equal(tidyPath("./notes/./april"), "notes/april", "current-directory dots are dropped");
assert.equal(tidyPath("notes/drafts/../april"), "notes/april", "a step up discards the last kept segment");
assert.equal(tidyPath("logs/.."), ".", "a path that cancels out is a single dot");
assert.equal(tidyPath("."), ".", "a lone dot stays a dot");
assert.equal(tidyPath("a/b/../../c"), "c", "steps up chain one after another");
assert.throws(() => tidyPath(9), Error, "a non-string path is rejected");
assert.throws(() => tidyPath(""), Error, "an empty path is rejected");
assert.throws(() => tidyPath("/notes"), Error, "a leading slash is rejected");
assert.throws(() => tidyPath("notes//april"), Error, "a doubled slash is rejected");
assert.throws(() => tidyPath("notes/../.."), Error, "climbing above the start is rejected");
console.log("ok");
