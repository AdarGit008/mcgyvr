import assert from "node:assert/strict";
import { auditLinkSetup } from "./solution.ts";

const rec = (side, verb, seq) => ({ side, verb, seq });
const setup = [
  rec("caller", "PROBE", 1),
  rec("listener", "READY", 1),
  rec("caller", "KEY", 2),
  rec("listener", "SEAL", 2),
];

assert.equal(
  auditLinkSetup([...setup, rec("caller", "CLOSE", 3), rec("listener", "CLOSE", 3)]),
  "",
  "a run with no pings is faultless"
);
assert.equal(
  auditLinkSetup([
    ...setup,
    rec("caller", "PING", 3),
    rec("listener", "PONG", 3),
    rec("caller", "CLOSE", 4),
    rec("listener", "CLOSE", 4),
  ]),
  "",
  "one ping and its answer are faultless"
);
assert.equal(
  auditLinkSetup([
    ...setup,
    rec("caller", "PING", 3),
    rec("listener", "PONG", 3),
    rec("caller", "PING", 4),
    rec("listener", "PONG", 4),
    rec("caller", "CLOSE", 5),
    rec("listener", "CLOSE", 5),
  ]),
  "",
  "the counter climbs by one on every caller record"
);
assert.equal(auditLinkSetup(setup), "short", "a run that stops after the seal");
assert.equal(
  auditLinkSetup([...setup, rec("caller", "CLOSE", 3)]),
  "short",
  "the listener's CLOSE is still owed"
);
assert.equal(
  auditLinkSetup([rec("caller", "PROBE", 0)]),
  "PROBE@1",
  "the probe must carry counter one"
);
assert.equal(
  auditLinkSetup([rec("listener", "PROBE", 1)]),
  "PROBE@1",
  "the caller opens the run"
);
assert.equal(
  auditLinkSetup([rec("caller", "PROBE", 1), rec("listener", "READY", 2)]),
  "READY@2",
  "the ready repeats the probe's counter"
);
assert.equal(
  auditLinkSetup([
    rec("caller", "PROBE", 1),
    rec("listener", "READY", 1),
    rec("caller", "KEY", 5),
  ]),
  "KEY@3",
  "the key carries exactly one more"
);
assert.equal(
  auditLinkSetup([...setup, rec("listener", "PONG", 3)]),
  "PONG@5",
  "a pong with no ping before it"
);
assert.equal(
  auditLinkSetup([...setup, rec("caller", "PING", 3), rec("caller", "CLOSE", 4)]),
  "CLOSE@6",
  "the listener owes a pong before the close"
);
assert.equal(
  auditLinkSetup([
    ...setup,
    rec("caller", "CLOSE", 3),
    rec("listener", "CLOSE", 4),
  ]),
  "CLOSE@6",
  "the answering close repeats the counter"
);
assert.equal(
  auditLinkSetup([
    ...setup,
    rec("caller", "CLOSE", 3),
    rec("listener", "CLOSE", 3),
    rec("caller", "PING", 4),
  ]),
  "PING@7",
  "nothing belongs after the run is over"
);

assert.throws(
  () => auditLinkSetup("PROBE"),
  Error,
  "a list that is not a list is rejected"
);
assert.throws(() => auditLinkSetup([]), Error, "an empty list is rejected");
assert.throws(
  () => auditLinkSetup([["caller", "PROBE", 1]]),
  Error,
  "a record that is not a mapping is rejected"
);
assert.throws(
  () => auditLinkSetup([rec("relay", "PROBE", 1)]),
  Error,
  "an unknown side is rejected"
);
assert.throws(
  () => auditLinkSetup([rec("caller", "HELLO", 1)]),
  Error,
  "a verb outside the seven is rejected"
);
assert.throws(
  () => auditLinkSetup([rec("caller", "PROBE", "1")]),
  Error,
  "a seq that is not a number is rejected"
);
assert.throws(
  () => auditLinkSetup([rec("caller", "PROBE", 1.5)]),
  Error,
  "a seq that is not whole is rejected"
);

console.log("ok");
