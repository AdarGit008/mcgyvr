import assert from "node:assert/strict";
import { createLruCache } from "./solution.ts";

const cache = createLruCache(2);
assert.equal(cache.size(), 0, "starts empty");
cache.put("a", 1);
cache.put("b", 2);
assert.equal(cache.get("a"), 1, "basic get");
cache.put("c", 3); // "b" is now least recently used and must be evicted
assert.equal(cache.get("b"), undefined, "get refreshed a, so b was evicted");
assert.equal(cache.get("a"), 1, "a survives");
assert.equal(cache.get("c"), 3, "c stored");
assert.equal(cache.size(), 2, "size capped at capacity");

const c2 = createLruCache(2);
c2.put("x", 10);
c2.put("y", 20);
c2.put("x", 11); // update refreshes recency, so "y" is now oldest
c2.put("z", 30);
assert.equal(c2.get("y"), undefined, "put on existing key refreshed it, y evicted");
assert.equal(c2.get("x"), 11, "updated value returned");
assert.equal(c2.get("z"), 30, "newest entry present");

const c3 = createLruCache(1);
c3.put("only", 0);
assert.equal(c3.get("only"), 0, "stored 0 is returned, not undefined");
c3.put("next", 5);
assert.equal(c3.get("only"), undefined, "capacity one evicts on every new key");
assert.equal(c3.size(), 1, "capacity one holds one entry");

assert.equal(createLruCache(3).get("missing"), undefined, "absent key is undefined");

assert.throws(() => createLruCache(0), Error, "zero capacity throws");
assert.throws(() => createLruCache(2.5), Error, "fractional capacity throws");
assert.throws(() => createLruCache(-1), Error, "negative capacity throws");
