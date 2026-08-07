const VERBS = ["open", "pin", "unpin", "forget"];

export function replayRecentPanel(limit: number, events: string[][]): string[] {
  if (typeof limit !== "number" || !Number.isInteger(limit) || limit < 1) {
    throw new Error("the limit must be a whole number of at least 1");
  }
  if (!Array.isArray(events)) {
    throw new Error("the events must be a list of pairs");
  }

  const pinned: string[] = [];
  let recent: string[] = [];

  const trim = () => {
    while (recent.length > limit) {
      recent.pop();
    }
  };

  for (const event of events) {
    if (!Array.isArray(event) || event.length !== 2) {
      throw new Error("an event is a [verb, name] pair");
    }
    const verb = event[0];
    const name = event[1];
    if (typeof verb !== "string" || !VERBS.includes(verb)) {
      throw new Error("a verb is one of open, pin, unpin and forget");
    }
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a name must be a non-empty string");
    }

    const pinnedAt = pinned.indexOf(name);
    if (verb === "open") {
      if (pinnedAt !== -1) {
        continue;
      }
      recent = recent.filter((held) => held !== name);
      recent.unshift(name);
      trim();
    } else if (verb === "pin") {
      if (pinnedAt !== -1) {
        continue;
      }
      recent = recent.filter((held) => held !== name);
      pinned.push(name);
    } else if (verb === "unpin") {
      if (pinnedAt === -1) {
        continue;
      }
      pinned.splice(pinnedAt, 1);
      recent.unshift(name);
      trim();
    } else {
      if (pinnedAt !== -1) {
        continue;
      }
      recent = recent.filter((held) => held !== name);
    }
  }

  return [...pinned, ...recent];
}
