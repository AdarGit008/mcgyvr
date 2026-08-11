import assert from "node:assert/strict";
import { traceRelay } from "./solution.ts";

assert.deepEqual(traceRelay({ depot: "" }, "depot"), ["depot"], "a terminal start walks itself");
assert.deepEqual(traceRelay({ gate: "depot", depot: "" }, "gate"), ["gate", "depot"], "one hand-off");
assert.deepEqual(
  traceRelay({ gate: "depot", depot: "" }, "depot"),
  ["depot"],
  "starting mid-chain skips earlier stations",
);
assert.deepEqual(
  traceRelay({ dock: "yard", pier: "dock", yard: "hub", hub: "" }, "pier"),
  ["pier", "dock", "yard", "hub"],
  "a long chain arrives in hand-off order",
);
assert.deepEqual(
  traceRelay({ north: "hub", south: "hub", hub: "" }, "south"),
  ["south", "hub"],
  "an unused branch stays out of the walk",
);
assert.deepEqual(
  traceRelay({ north: "hub", south: "hub", hub: "" }, "north"),
  ["north", "hub"],
  "each branch walks through the shared tail",
);
assert.throws(() => traceRelay({ depot: "" }, "gate"), Error, "an unknown start is rejected");
assert.throws(() => traceRelay({ depot: "" }, 42), Error, "a non-string start is rejected");
assert.throws(() => traceRelay({ gate: "yard" }, "gate"), Error, "a link to a missing station is rejected");
assert.throws(
  () => traceRelay({ gate: "depot", depot: "gate" }, "gate"),
  Error,
  "a two-station circle is rejected",
);
assert.throws(() => traceRelay({ loop: "loop" }, "loop"), Error, "a station handing to itself is rejected");
assert.throws(
  () => traceRelay({ "": "depot", depot: "" }, "depot"),
  Error,
  "an empty station name is rejected",
);
assert.throws(
  () => traceRelay({ gate: null, depot: "" }, "depot"),
  Error,
  "a non-string link is rejected",
);
console.log("ok");
