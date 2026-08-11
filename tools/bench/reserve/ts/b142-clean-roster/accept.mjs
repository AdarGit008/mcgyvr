import assert from "node:assert/strict";
import { cleanRoster } from "./solution.ts";

assert.deepEqual(cleanRoster([]), [], "an empty sheet stays empty");
assert.deepEqual(cleanRoster(["Rosa Vane"]), ["Rosa Vane"], "a tidy entry is unchanged");
assert.deepEqual(cleanRoster(["  Piet   Aker "]), ["Piet Aker"], "spacing is trimmed and collapsed");
assert.deepEqual(cleanRoster(["Mo\tPine"]), ["Mo Pine"], "a tab collapses to one space");
assert.deepEqual(cleanRoster(["Ana Reyes", "ANA REYES"]), ["Ana Reyes"], "a case-insensitive repeat keeps the first spelling");
assert.deepEqual(cleanRoster(["Kit Snow", "Kit  Snow"]), ["Kit Snow"], "a repeat appearing after cleaning is dropped");
assert.deepEqual(cleanRoster(["Zia Kade", "Ann Bell", "zia kade"]), ["Zia Kade", "Ann Bell"], "first-appearance order is kept");
assert.throws(() => cleanRoster(42), Error, "a non-list is rejected");
assert.throws(() => cleanRoster([7]), Error, "a non-string entry is rejected");
assert.throws(() => cleanRoster(["   "]), Error, "a whitespace-only entry is rejected");
assert.throws(() => cleanRoster([""]), Error, "an empty entry is rejected");
console.log("ok");
