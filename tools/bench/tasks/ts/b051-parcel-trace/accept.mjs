import assert from "node:assert/strict";
import { traceParcel } from "./solution.ts";

assert.deepEqual(traceParcel([]), ["created"], "no events yields the start state");
assert.deepEqual(traceParcel(["pack"]), ["created", "packed"], "one event");
assert.deepEqual(
  traceParcel(["pack", "ship", "deliver"]),
  ["created", "packed", "shipped", "delivered"],
  "the delivery path",
);
assert.deepEqual(
  traceParcel(["pack", "ship", "bounce"]),
  ["created", "packed", "shipped", "returned"],
  "the return path",
);
assert.throws(() => traceParcel("pack"), Error, "non-list argument is rejected");
assert.throws(() => traceParcel(["melt"]), Error, "unknown event is rejected");
assert.throws(() => traceParcel(["ship"]), Error, "ship before pack is rejected");
assert.throws(() => traceParcel(["pack", "pack"]), Error, "repeated event is rejected");
assert.throws(
  () => traceParcel(["pack", "ship", "deliver", "pack"]),
  Error,
  "an event after a final state is rejected",
);
console.log("ok");
