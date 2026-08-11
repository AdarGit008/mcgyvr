import assert from "node:assert/strict";
import { resolveLayers } from "./solution.ts";

const plain = (set, drop = [], lock = []) => ({ set, drop, lock });

assert.deepEqual(resolveLayers([]), {}, "no layers settle nothing");
assert.deepEqual(resolveLayers([plain({ mode: "fast", tint: "warm" })]), { mode: "fast", tint: "warm" }, "a lone layer settles its assignments");
assert.deepEqual(resolveLayers([plain({ mode: "fast" }), plain({ mode: "safe" })]), { mode: "safe" }, "a later layer beats an earlier one");
assert.deepEqual(resolveLayers([plain({ mode: "fast" }, [], ["mode"]), plain({ mode: "safe" })]), { mode: "fast" }, "a lock in force refuses a later assignment");
assert.deepEqual(resolveLayers([plain({ mode: "fast", tint: "warm" }), plain({}, ["tint"])]), { mode: "fast" }, "a removal takes a settled name away");
assert.deepEqual(resolveLayers([plain({ tint: "warm" }, [], ["tint"]), plain({}, ["tint"])]), { tint: "warm" }, "a lock in force refuses a later removal");
assert.deepEqual(resolveLayers([plain({}, [], ["tint"]), plain({ tint: "warm" })]), {}, "a name locked before assignment stays absent");
console.log("ok");
