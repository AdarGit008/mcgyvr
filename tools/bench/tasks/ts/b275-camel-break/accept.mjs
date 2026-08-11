import assert from "node:assert/strict";
import { camelBreak } from "./solution.ts";

assert.deepEqual(camelBreak("orderId"), ["order", "id"], "a capital opens a word");
assert.deepEqual(camelBreak("id"), ["id"], "no capitals, one word");
assert.deepEqual(camelBreak("OrderId"), ["order", "id"], "a leading capital adds nothing");
assert.deepEqual(camelBreak("abc"), ["abc"], "a plain word");
assert.deepEqual(camelBreak(""), [], "nothing to break");
assert.deepEqual(camelBreak("aBcD"), ["a", "bc", "d"], "several short words");
assert.deepEqual(camelBreak("http2Server"), ["http2", "server"], "a digit opens nothing");
console.log("ok");
