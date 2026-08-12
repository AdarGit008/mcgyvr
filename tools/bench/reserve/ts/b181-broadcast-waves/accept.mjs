import assert from "node:assert/strict";
import { broadcastWaves } from "./solution.ts";

assert.equal(broadcastWaves(["a>b", "b>c"], "a"), "a\nb\nc", "a plain chain gives one desk per wave");
assert.equal(broadcastWaves(["a>c", "a>b"], "a"), "a\nb, c", "a wave lists its desks alphabetically");
assert.equal(broadcastWaves(["a>b", "a>c", "b>d", "c>d"], "a"), "a\nb, c\nd", "a desk joins only its earliest wave");
assert.equal(broadcastWaves([], "desk"), "desk", "a start with no links is a single wave");
assert.equal(broadcastWaves(["a>b", "x>y"], "a"), "a\nb", "desks the bulletin never reaches are left out");
assert.equal(broadcastWaves(["a>b", "b>a"], "a"), "a\nb", "a link back to the start ends the spread");
assert.throws(() => broadcastWaves(["a-b"], "a"), Error, "a link without sender>receiver is rejected");
console.log("ok");
