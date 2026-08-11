import assert from "node:assert/strict";
import { trayPush, trayTop } from "./solution.ts";

const held = ["a"];
assert.deepEqual(trayPush([], "a"), ["a"], "the first item");
assert.deepEqual(trayPush(held, "b"), ["a", "b"], "the new item rests on top");
assert.deepEqual(held, ["a"], "the original stack is untouched");
assert.equal(trayTop(["a", "b"]), "b", "the top is the last pushed");
assert.equal(trayTop(["z"]), "z", "a lone item is the top");
assert.equal(trayTop([]), null, "an empty stack has no top");
console.log("ok");
