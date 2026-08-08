export function finalDoorState(events: string[]): string {
  const lawful: Record<string, Record<string, string>> = {
    unlock: { locked: "closed" },
    lock: { closed: "locked" },
    open: { closed: "open" },
    close: { open: "closed" },
  };
  let state = "locked";
  let ignored = 0;
  for (const event of events) {
    const moves = lawful[event];
    if (moves === undefined) {
      throw new Error(`unknown event ${event}`);
    }
    const next = moves[state];
    if (next === undefined) {
      ignored += 1;
    } else {
      state = next;
    }
  }
  return state + ":" + ignored;
}
