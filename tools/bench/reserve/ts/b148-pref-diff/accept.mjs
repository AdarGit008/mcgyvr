import assert from "node:assert/strict";
import { diffPaths } from "./solution.ts";

assert.deepEqual(diffPaths({}, {}), [], "identical empty trees differ nowhere");
assert.deepEqual(diffPaths({ theme: "mono" }, { theme: "mono" }), [], "an unchanged leaf is not reported");
assert.deepEqual(diffPaths({ theme: "mono" }, { theme: "sepia" }), ["theme"], "a changed leaf reports its key");
assert.deepEqual(diffPaths({ old: "1" }, { fresh: "2" }), ["fresh", "old"], "keys on only one side are reported, sorted");
assert.deepEqual(diffPaths({ display: { theme: "mono", scale: "2" } }, { display: { theme: "sepia", scale: "2" } }), ["display/theme"], "a change inside matching sections joins keys with slashes");
assert.deepEqual(diffPaths({ sound: "on" }, { sound: { alarm: "on" } }), ["sound"], "a leaf facing a section reports the path itself");
assert.deepEqual(diffPaths({ b: { z: "1" }, a: "x" }, { b: { z: "2" }, a: "y" }), ["a", "b/z"], "reported paths come out sorted across levels");
assert.throws(() => diffPaths("flat", {}), Error, "a before that is not a mapping is rejected");
assert.throws(() => diffPaths({}, 7), Error, "an after that is not a mapping is rejected");
assert.throws(() => diffPaths({ scale: 2 }, { scale: 2 }), Error, "a numeric leaf is rejected even when both sides match");
assert.throws(() => diffPaths({}, { dark: true }), Error, "a boolean leaf is rejected");
console.log("ok");
