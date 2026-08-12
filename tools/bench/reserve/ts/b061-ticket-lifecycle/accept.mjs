import assert from "node:assert/strict";
import { replayTicket } from "./solution.ts";

assert.equal(replayTicket([]), "new", "empty log leaves the ticket new");
assert.equal(replayTicket(["triage"]), "triaged", "triage moves a new ticket");
assert.equal(replayTicket(["triage", "resolve"]), "resolved", "resolve after triage");
assert.equal(
  replayTicket(["triage", "resolve", "reopen"]),
  "triaged",
  "reopen returns the ticket to triaged",
);
assert.equal(
  replayTicket(["triage", "resolve", "reopen", "resolve"]),
  "resolved",
  "a reopened ticket can resolve again",
);
assert.equal(
  replayTicket(["triage", "resolve", "archive"]),
  "archived",
  "archive closes a resolved ticket",
);
assert.throws(() => replayTicket(["resolve"]), Error, "resolve is not lawful for a new ticket");
assert.throws(() => replayTicket(["triage", "triage"]), Error, "triage cannot repeat");
assert.throws(() => replayTicket(["escalate"]), Error, "unknown event is rejected");
assert.throws(
  () => replayTicket(["triage", "resolve", "archive", "reopen"]),
  Error,
  "archived is final",
);
console.log("ok");
