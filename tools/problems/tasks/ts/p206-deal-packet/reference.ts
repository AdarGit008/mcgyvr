function callCycle(order: string, count: number): number[] {
  const up: number[] = [];
  for (let at = 0; at < count; at += 1) up.push(at);
  if (order === "round") return up;
  if (order === "reverse") return up.slice().reverse();
  return up.concat(up.slice().reverse());
}

export function dealPacket(
  items: string[],
  seats: number[],
  order: string,
): Record<string, unknown> {
  if (!Array.isArray(items)) {
    throw new Error("the packet must be a list");
  }
  const seen = new Set<string>();
  for (const item of items) {
    if (typeof item !== "string" || item.length === 0) {
      throw new Error("every packet entry must be a non-empty string");
    }
    if (seen.has(item)) {
      throw new Error("the packet repeats " + item);
    }
    seen.add(item);
  }
  if (!Array.isArray(seats) || seats.length === 0) {
    throw new Error("the limits must be a non-empty list");
  }
  for (const limit of seats) {
    if (typeof limit !== "number" || !Number.isInteger(limit) || limit < 1) {
      throw new Error("every limit must be a whole number above zero");
    }
  }
  if (order !== "round" && order !== "reverse" && order !== "snake") {
    throw new Error("unknown turn sequence: " + String(order));
  }

  const cycle = callCycle(order, seats.length);
  const hands: string[][] = seats.map(() => []);
  const left: string[] = [];
  let room = seats.reduce((sum, limit) => sum + limit, 0);
  let at = 0;
  for (const item of items) {
    if (room === 0) {
      left.push(item);
      continue;
    }
    while (hands[cycle[at % cycle.length]].length >= seats[cycle[at % cycle.length]]) {
      at += 1;
    }
    hands[cycle[at % cycle.length]].push(item);
    at += 1;
    room -= 1;
  }
  return { hands, left };
}
