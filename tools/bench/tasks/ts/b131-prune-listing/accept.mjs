import assert from "node:assert/strict";
import { pruneListing } from "./solution.ts";

assert.deepEqual(pruneListing(["a.txt", "b.txt"], []), ["a.txt", "b.txt"], "no rules keeps everything");
assert.deepEqual(
  pruneListing(["cache", "cache/one.txt", "cachet.txt"], ["cache"]),
  ["cachet.txt"],
  "a directory rule covers itself and its contents",
);
assert.deepEqual(
  pruneListing(["notes.tmp", "deep/notes.tmp", "tmp.notes"], ["*.tmp"]),
  ["deep/notes.tmp", "tmp.notes"],
  "a star rule matches from the top, inside one segment",
);
assert.deepEqual(
  pruneListing(["kits/a.raw", "kits/sub/b.raw"], ["kits/*.raw"]),
  ["kits/sub/b.raw"],
  "a star never crosses into a deeper segment",
);
assert.deepEqual(
  pruneListing(["logs/keep.txt", "logs/spill.txt", "readme.md"], ["logs", "!logs/keep.txt"]),
  ["logs/keep.txt", "readme.md"],
  "a later keep rule overrides an earlier drop",
);
assert.deepEqual(
  pruneListing(["logs/keep.txt"], ["!logs/keep.txt", "logs"]),
  [],
  "the last matching rule decides",
);
assert.deepEqual(
  pruneListing(["pkg/a.js", "pkg/b.js"], ["pkg", "!pkg/b*"]),
  ["pkg/b.js"],
  "a keep rule may use a star",
);
assert.deepEqual(pruneListing(["free.txt"], ["bound.txt"]), ["free.txt"], "an unmatched path survives");
assert.deepEqual(pruneListing(["tmp", "tmp9"], ["tmp*"]), [], "a star may match nothing");
assert.deepEqual(pruneListing(["mycache1/x"], ["*cache*"]), [], "two stars in one segment");
assert.deepEqual(pruneListing([], ["x"]), [], "an empty listing stays empty");
assert.throws(() => pruneListing([42], []), Error, "non-string path is rejected");
assert.throws(() => pruneListing([""], []), Error, "empty path is rejected");
assert.throws(() => pruneListing(["a//b"], []), Error, "doubled slash in a path is rejected");
assert.throws(() => pruneListing(["/lead"], []), Error, "leading slash is rejected");
assert.throws(() => pruneListing(["a.txt"], [7]), Error, "non-string rule is rejected");
assert.throws(() => pruneListing(["a.txt"], [""]), Error, "empty rule is rejected");
assert.throws(() => pruneListing(["a.txt"], ["!"]), Error, "bare exclamation mark is rejected");
assert.throws(() => pruneListing(["a.txt"], ["x//y"]), Error, "empty pattern segment is rejected");
console.log("ok");
