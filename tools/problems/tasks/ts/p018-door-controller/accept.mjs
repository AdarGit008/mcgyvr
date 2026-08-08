import assert from "node:assert/strict";
import { finalDoorState } from "./solution.ts";

assert.equal(finalDoorState([]), "locked:0", "no events, still locked");
assert.equal(finalDoorState(["unlock"]), "closed:0", "unlock releases the lock");
assert.equal(finalDoorState(["unlock", "open"]), "open:0", "unlock then open");
assert.equal(finalDoorState(["open"]), "locked:1", "a locked door does not open");
assert.equal(
  finalDoorState(["unlock", "open", "open"]),
  "open:1",
  "opening an open door is ignored",
);
assert.equal(
  finalDoorState(["unlock", "open", "close", "lock"]),
  "locked:0",
  "a full lawful cycle",
);
assert.equal(
  finalDoorState(["lock", "close", "unlock"]),
  "closed:2",
  "only the last event applies",
);
assert.equal(
  finalDoorState(["unlock", "open", "unlock"]),
  "open:1",
  "unlock means nothing to an open door",
);
assert.throws(() => finalDoorState(["knock"]), Error, "unknown event rejected");
console.log("ok");
