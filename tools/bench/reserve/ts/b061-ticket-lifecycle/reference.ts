/** Replay a support ticket's lifecycle and report its final state. */

const TRANSITIONS: Record<string, Record<string, string>> = {
  new: { triage: "triaged" },
  triaged: { resolve: "resolved" },
  resolved: { reopen: "triaged", archive: "archived" },
  archived: {},
};

const EVENTS = new Set(["triage", "resolve", "reopen", "archive"]);

export function replayTicket(events: string[]): string {
  let state = "new";
  for (const event of events) {
    if (!EVENTS.has(event)) {
      throw new Error("unknown event: " + event);
    }
    const next = TRANSITIONS[state][event];
    if (next === undefined) {
      throw new Error(event + " is not lawful in state " + state);
    }
    state = next;
  }
  return state;
}
