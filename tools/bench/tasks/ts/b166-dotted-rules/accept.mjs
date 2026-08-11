import assert from "node:assert/strict";
import { matchSetting } from "./solution.ts";

assert.equal(matchSetting({ "editor.font": "mono", "editor.*": "serif" }, "editor.font"), "mono", "the exact selector beats a wildcard");
assert.equal(matchSetting({ "editor.*": "serif", "editor.font.*": "mono" }, "editor.font.size"), "mono", "the longer covering prefix wins");
assert.equal(matchSetting({ "*": "plain" }, "log.level"), "plain", "the lone star covers any name");
assert.equal(matchSetting({ "net.*": "fast", "*": "plain" }, "net.retry"), "fast", "a prefix wildcard beats the lone star");
assert.equal(matchSetting({ "editor.*": "serif" }, "net.retry"), null, "an uncovered name yields null");
assert.equal(matchSetting({ "editor.*": "serif" }, "editor"), null, "a wildcard does not cover its bare prefix");
assert.equal(matchSetting({}, "editor.font"), null, "no rules yields null");
assert.throws(() => matchSetting({ "*": "plain" }, 7), Error, "a non-string name is rejected");
assert.throws(() => matchSetting({ "*": "plain" }, ""), Error, "an empty name is rejected");
assert.throws(() => matchSetting({ "*": "plain" }, "a*b"), Error, "a name holding a star is rejected");
assert.throws(() => matchSetting({ "editor.*": 7 }, "editor.font"), Error, "a non-string rule value is rejected");
assert.throws(() => matchSetting({ "edi*tor.x": "v" }, "editor.font"), Error, "a misplaced star in a selector is rejected");
console.log("ok");
