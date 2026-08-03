import assert from "node:assert/strict";
import { binarySearch } from "./solution.ts";

const items = [1, 3, 5, 7, 9];
assert.equal(binarySearch(items, 5), 2, "a value in the middle");
assert.equal(binarySearch(items, 1), 0, "the first element");
assert.equal(binarySearch(items, 9), 4, "the last element — the bug's blind spot");
assert.equal(binarySearch(items, 4), -1, "an absent value between two present ones");
assert.equal(binarySearch(items, 100), -1, "past the end");
assert.equal(binarySearch(items, 0), -1, "before the start");

assert.equal(binarySearch([], 1), -1, "empty array");
assert.equal(binarySearch([42], 42), 0, "single element found");
assert.equal(binarySearch([42], 7), -1, "single element absent");
assert.equal(binarySearch([1, 2], 2), 1, "two elements, the later one");
