import assert from "node:assert/strict";
import { hasAll } from "./solution.ts";

assert.equal(hasAll({ a: 1, b: 2 }, ["a"]), true, "the key is held");
assert.equal(hasAll({ a: 1 }, ["a", "b"]), false, "one key is missing");
assert.equal(hasAll({}, []), true, "nothing is needed");
assert.equal(hasAll({}, ["a"]), false, "an empty store holds nothing");
assert.equal(hasAll({ a: 1 }, []), true, "a full store, nothing needed");
assert.equal(hasAll({ a: 1, b: 2 }, ["a", "b"]), true, "both keys are held");
console.log("ok");
