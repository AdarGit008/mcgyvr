import assert from "node:assert/strict";
import { rotaNext } from "./solution.ts";

assert.equal(rotaNext(["a", "b", "c"], "a"), "b", "the next name in order");
assert.equal(rotaNext(["a", "b", "c"], "b"), "c", "onward through the rota");
assert.equal(rotaNext(["a", "b", "c"], "c"), "a", "the last name comes round");
assert.equal(rotaNext(["solo"], "solo"), "solo", "a rota of one follows itself");
assert.equal(rotaNext(["a", "b"], "z"), "z", "a name not on the rota");
assert.equal(rotaNext([], "x"), "x", "an empty rota changes nothing");
console.log("ok");
