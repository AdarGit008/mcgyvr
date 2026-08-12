import assert from "node:assert/strict";
import { dayNext } from "./solution.ts";

assert.equal(dayNext(0, 1), 1, "tomorrow");
assert.equal(dayNext(1, 0), 6, "round the week");
assert.equal(dayNext(3, 3), 7, "today is a whole week away");
assert.equal(dayNext(6, 0), 1, "over the end of the week");
assert.equal(dayNext(0, 6), 6, "the far end of the week");
assert.equal(dayNext(2, 5), 3, "three days on");
console.log("ok");
