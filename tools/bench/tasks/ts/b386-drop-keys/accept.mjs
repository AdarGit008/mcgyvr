import assert from "node:assert/strict";
import { dropKeys } from "./solution.ts";

assert.deepEqual(dropKeys({ a: 1, b: 2 }, ["a"]), { b: 2 }, "the named key goes");
assert.deepEqual(dropKeys({ a: 1 }, ["b"]), { a: 1 }, "an absent key changes nothing");
assert.deepEqual(dropKeys({}, ["a"]), {}, "an empty store");
assert.deepEqual(dropKeys({ a: 1 }, ["a"]), {}, "everything is dropped");
assert.deepEqual(dropKeys({ a: 1, b: 2 }, []), { a: 1, b: 2 }, "nothing is named");

const source = { a: 1, b: 2 };
dropKeys(source, ["a"]);
assert.deepEqual(source, { a: 1, b: 2 }, "the store it was given is untouched");
console.log("ok");
