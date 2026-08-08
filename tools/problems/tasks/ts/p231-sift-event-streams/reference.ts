const RANK = ["chatter", "notice", "alarm", "panic"];

function isMapping(value: unknown): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function siftEventStreams(
  lanes: Array<Record<string, unknown>>,
  events: Array<Record<string, unknown>>,
): Record<string, unknown> {
  if (!Array.isArray(lanes)) throw new Error("the lanes must be a list");
  if (!Array.isArray(events)) throw new Error("the events must be a list");
  const names: string[] = [];
  const prefixes: string[] = [];
  const ceilings: number[] = [];
  const finals: boolean[] = [];
  const order: string[] = [];
  const took = new Map<string, number[]>();
  for (const lane of lanes) {
    if (!isMapping(lane)) throw new Error("a lane must be a mapping");
    const name = (lane as Record<string, unknown>).name;
    const prefix = (lane as Record<string, unknown>).prefix;
    const upTo = (lane as Record<string, unknown>).upTo;
    const last = (lane as Record<string, unknown>).last;
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a name must be a non-empty string");
    }
    if (typeof prefix !== "string") throw new Error("a prefix must be a string");
    if (typeof upTo !== "string" || !RANK.includes(upTo)) {
      throw new Error("a severity must be one of the four words");
    }
    if (typeof last !== "boolean") throw new Error("last is either true or false");
    if (!took.has(name)) {
      took.set(name, []);
      order.push(name);
    }
    names.push(name);
    prefixes.push(prefix);
    ceilings.push(RANK.indexOf(upTo));
    finals.push(last);
  }
  const dropped: number[] = [];
  for (let at = 0; at < events.length; at++) {
    const event = events[at];
    if (!isMapping(event)) throw new Error("an event must be a mapping");
    const channel = (event as Record<string, unknown>).channel;
    const severity = (event as Record<string, unknown>).severity;
    if (typeof channel !== "string" || channel.length === 0) {
      throw new Error("a channel must be a non-empty string");
    }
    if (typeof severity !== "string" || !RANK.includes(severity)) {
      throw new Error("a severity must be one of the four words");
    }
    const rank = RANK.indexOf(severity);
    let caught = false;
    for (let which = 0; which < names.length; which++) {
      if (!channel.startsWith(prefixes[which])) continue;
      if (rank > ceilings[which]) continue;
      const held = took.get(names[which]) as number[];
      if (held.length === 0 || held[held.length - 1] !== at) held.push(at);
      caught = true;
      if (finals[which]) break;
    }
    if (!caught) dropped.push(at);
  }
  return {
    lanes: order.map((name) => ({ name, took: took.get(name) as number[] })),
    dropped,
  };
}
