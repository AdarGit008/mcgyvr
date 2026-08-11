import assert from "node:assert/strict";
import { scanManifest } from "./solution.ts";

assert.deepEqual(
  scanManifest("8ff2 pump.log", { "pump.log": "seal ok" }),
  { intact: ["pump.log"], altered: [], lost: [], strays: [] },
  "a matching digest is intact",
);
assert.deepEqual(
  scanManifest("ffff pump.log", { "pump.log": "seal ok" }),
  { intact: [], altered: ["pump.log"], lost: [], strays: [] },
  "a differing digest is altered",
);
assert.deepEqual(
  scanManifest("d952 tally.csv", {}),
  { intact: [], altered: [], lost: ["tally.csv"], strays: [] },
  "a listed file not held is lost",
);
assert.deepEqual(
  scanManifest("", { "attic.txt": "x" }),
  { intact: [], altered: [], lost: [], strays: ["attic.txt"] },
  "a held file never listed is a stray",
);
assert.deepEqual(
  scanManifest("", {}),
  { intact: [], altered: [], lost: [], strays: [] },
  "nothing listed, nothing held",
);
assert.deepEqual(
  scanManifest("8ff2 pump.log\n0001 rounds.txt\nddd4 gone.md", {
    "pump.log": "seal ok",
    "rounds.txt": "west wing clear",
    "attic.txt": "x",
  }),
  { intact: ["pump.log"], altered: ["rounds.txt"], lost: ["gone.md"], strays: ["attic.txt"] },
  "all four kinds report together",
);
assert.deepEqual(
  scanManifest("\n8ff2 pump.log\n\n", { "pump.log": "seal ok" }),
  { intact: ["pump.log"], altered: [], lost: [], strays: [] },
  "blank manifest lines are ignored",
);
assert.deepEqual(
  scanManifest("0078 field notes.txt", { "field notes.txt": "x" }),
  { intact: ["field notes.txt"], altered: [], lost: [], strays: [] },
  "a file name may contain spaces",
);
assert.deepEqual(
  scanManifest("0000 blank.cfg", { "blank.cfg": "" }),
  { intact: ["blank.cfg"], altered: [], lost: [], strays: [] },
  "empty content digests to 0000",
);
assert.deepEqual(
  scanManifest("", { "loft.txt": "x", "attic.txt": "x" }),
  { intact: [], altered: [], lost: [], strays: ["attic.txt", "loft.txt"] },
  "each list is sorted alphabetically",
);
assert.throws(() => scanManifest(42, {}), Error, "non-string manifest is rejected");
assert.throws(() => scanManifest("8ff2", {}), Error, "a line with no space is rejected");
assert.throws(() => scanManifest("zz pump.log", {}), Error, "a short digest is rejected");
assert.throws(() => scanManifest("wxyz pump.log", {}), Error, "non-hex digest is rejected");
assert.throws(() => scanManifest("8FF2 pump.log", {}), Error, "uppercase digest is rejected");
assert.throws(() => scanManifest("8ff2 ", {}), Error, "a line naming no file is rejected");
assert.throws(
  () => scanManifest("8ff2 pump.log\n8ff2 pump.log", {}),
  Error,
  "a file listed twice is rejected",
);
assert.throws(() => scanManifest("", { "junk.bin": 7 }), Error, "non-string content is rejected");
console.log("ok");
