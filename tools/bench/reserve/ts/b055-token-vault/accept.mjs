import assert from "node:assert/strict";
import { tokenFetch, tokenSave } from "./solution.ts";

const vault = {};
tokenSave(vault, "auth", "abc", 10, 5);
assert.deepEqual(vault, { auth: ["abc", 15] }, "save records the value and its expiry tick");
assert.equal(tokenFetch(vault, "auth", 14), "abc", "the last tick before expiry still hits");
assert.equal(tokenFetch(vault, "auth", 15), null, "the expiry tick itself misses");
assert.deepEqual(vault, {}, "an expired entry is removed by the fetch");
assert.equal(tokenFetch({}, "ghost", 0), null, "a name never held misses");

const second = {};
tokenSave(second, "job", "one", 0, 10);
tokenSave(second, "job", "two", 5, 3);
assert.equal(tokenFetch(second, "job", 7), "two", "saving again replaces value and expiry");

assert.throws(() => tokenSave({}, "k", "v", 0, 0), Error, "a zero ttl is rejected");
assert.throws(() => tokenSave({}, "k", "v", 1.5, 3), Error, "a fractional now is rejected");
assert.throws(() => tokenSave({}, "", "v", 0, 3), Error, "an empty name is rejected");
console.log("ok");
