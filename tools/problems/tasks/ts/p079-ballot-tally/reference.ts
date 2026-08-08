export function tallyBallots(
  events: Array<Record<string, string>>
): Record<string, number> {
  const standing: Record<string, string> = {};
  const seen = new Set<string>();
  let closed = false;
  for (const event of events) {
    if (closed) {
      throw new Error("event after close");
    }
    if (event.type === "cast") {
      if (event.voter in standing) {
        throw new Error("voter already has a standing vote");
      }
      standing[event.voter] = event.option;
      seen.add(event.option);
    } else if (event.type === "retract") {
      if (!(event.voter in standing)) {
        throw new Error("no standing vote to retract");
      }
      delete standing[event.voter];
    } else if (event.type === "close") {
      closed = true;
    } else {
      throw new Error("unknown event type: " + event.type);
    }
  }
  const counts: Record<string, number> = {};
  for (const option of seen) {
    counts[option] = 0;
  }
  for (const voter of Object.keys(standing)) {
    counts[standing[voter]] += 1;
  }
  return counts;
}
