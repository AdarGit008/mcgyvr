export function assignBerths(
  berths: Array<{ id: string; size: number }>,
  quota: Record<string, number>,
  requests: Array<Record<string, unknown>>
): string[] {
  const ids = new Set<string>();
  for (const berth of berths) {
    if (ids.has(berth.id)) {
      throw new Error("duplicate berth id: " + berth.id);
    }
    ids.add(berth.id);
  }
  const occupant: Array<string | null> = berths.map(() => null);
  const docked: Record<string, { berth: number; owner: string }> = {};
  const held: Record<string, number> = {};
  const results: string[] = [];
  for (const request of requests) {
    const op = request.op;
    if (op === "dock") {
      const boat = request.boat as string;
      const owner = request.owner as string;
      const size = request.size as number;
      if (boat in docked) {
        results.push("rejected:already_docked");
        continue;
      }
      const limit = owner in quota ? quota[owner] : Infinity;
      if ((held[owner] ?? 0) >= limit) {
        results.push("rejected:over_quota");
        continue;
      }
      let chosen = -1;
      for (let i = 0; i < berths.length; i++) {
        if (occupant[i] === null && berths[i].size >= size) {
          chosen = i;
          break;
        }
      }
      if (chosen === -1) {
        results.push("rejected:no_berth");
        continue;
      }
      occupant[chosen] = boat;
      docked[boat] = { berth: chosen, owner };
      held[owner] = (held[owner] ?? 0) + 1;
      results.push(berths[chosen].id);
    } else if (op === "leave") {
      const boat = request.boat as string;
      if (!(boat in docked)) {
        results.push("rejected:not_docked");
        continue;
      }
      const { berth, owner } = docked[boat];
      occupant[berth] = null;
      held[owner] -= 1;
      delete docked[boat];
      results.push("left");
    } else {
      throw new Error("unknown op: " + String(op));
    }
  }
  return results;
}
