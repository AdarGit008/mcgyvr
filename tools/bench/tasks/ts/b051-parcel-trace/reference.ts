const MOVES: Record<string, Record<string, string>> = {
  created: { pack: "packed" },
  packed: { ship: "shipped" },
  shipped: { deliver: "delivered", bounce: "returned" },
};

const KNOWN = new Set(["pack", "ship", "deliver", "bounce"]);

export function traceParcel(events: string[]): string[] {
  if (!Array.isArray(events)) {
    throw new Error("traceParcel expects a list of events");
  }
  let state = "created";
  const trail = [state];
  for (const event of events) {
    if (typeof event !== "string" || !KNOWN.has(event)) {
      throw new Error("unknown event: " + String(event));
    }
    const next = (MOVES[state] ?? {})[event];
    if (next === undefined) {
      throw new Error(event + " is not allowed in state " + state);
    }
    state = next;
    trail.push(state);
  }
  return trail;
}
