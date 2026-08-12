import assert from "node:assert/strict";
import { queueCall } from "./solution.ts";

assert.equal(queueCall(["a", "b", "c"], [], "a"), "b", "the very next ticket");
assert.equal(queueCall(["a", "b", "c"], ["b"], "a"), "c", "a withdrawn ticket is passed");
assert.equal(queueCall(["a", "b"], [], "b"), null, "nothing follows the last");
assert.equal(queueCall(["a", "b"], ["b"], "a"), null, "the only follower withdrew");
assert.equal(
  queueCall(["a", "b", "c", "d"], ["b", "c"], "a"),
  "d",
  "two withdrawals in a row",
);
assert.equal(queueCall(["a"], [], "a"), null, "a queue of one");
console.log("ok");
