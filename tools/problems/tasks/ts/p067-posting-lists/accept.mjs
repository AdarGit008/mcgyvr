import assert from "node:assert/strict";
import { postingLists } from "./solution.ts";

assert.deepEqual(
  postingLists(["The quick fox", "a fox! A FOX.", "42 x-rays 42", ""]),
  { the: [0], quick: [0], fox: [0, 1], rays: [2] },
  "folds case, drops digit-only and single-character terms",
);
assert.deepEqual(
  postingLists(["Don't stop"]),
  { don: [0], stop: [0] },
  "an apostrophe splits a word",
);
assert.deepEqual(
  postingLists(["beta", "alpha", "beta alpha"]),
  { beta: [0, 2], alpha: [1, 2] },
  "positions ascend within each list",
);
assert.deepEqual(
  postingLists(["Fox fox FOX"]),
  { fox: [0] },
  "repeats within one document collapse",
);
assert.deepEqual(postingLists([]), {}, "no documents, empty index");
assert.deepEqual(postingLists(["", "..."]), {}, "wordless documents index nothing");
assert.throws(() => postingLists([3]), Error, "non-string document rejected");
assert.throws(() => postingLists("abc"), Error, "bare string input rejected");
console.log("ok");
