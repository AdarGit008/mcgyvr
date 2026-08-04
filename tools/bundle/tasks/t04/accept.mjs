import assert from "node:assert/strict";
import { LruCache } from "./solution.ts";

const cache = new LruCache(2);
assert.equal(cache.size, 0, "starts empty");
cache.set("a", 1);
cache.set("b", 2);
assert.equal(cache.get("a"), 1, "stored value comes back");
assert.equal(cache.size, 2, "size counts entries");

cache.set("c", 3); // "b" is now least recently used: "a" was just read.
assert.equal(cache.get("b"), undefined, "least recently used entry was evicted");
assert.equal(cache.get("a"), 1, "recently used entry survived");
assert.equal(cache.get("c"), 3, "newest entry present");
assert.equal(cache.size, 2, "size never exceeds capacity");

const updating = new LruCache(2);
updating.set("x", 1);
updating.set("y", 2);
updating.set("x", 10);
updating.set("z", 3);
assert.equal(updating.get("x"), 10, "set counts as a use and updates in place");
assert.equal(updating.get("y"), undefined, "the stale entry was the one evicted");
assert.equal(updating.size, 2, "an update does not grow the cache");

const one = new LruCache(1);
one.set("only", "value");
one.set("next", "value2");
assert.equal(one.get("only"), undefined, "capacity one evicts on every insert");
assert.equal(one.get("next"), "value2", "the newest entry is kept");

assert.equal(new LruCache(2).get("missing"), undefined, "missing key is undefined");

for (const bad of [0, -1, 1.5, "2"]) {
  assert.throws(() => new LruCache(bad), Error, `capacity ${JSON.stringify(bad)} throws`);
}
