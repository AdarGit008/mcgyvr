type Wave = { name: string; refs: string[]; lines: number; zones: string[] };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

export function buildPickWaves(
  orders: unknown,
  limits: Record<string, unknown>,
): Record<string, unknown> {
  if (limits === null || typeof limits !== "object" || Array.isArray(limits)) {
    throw new Error("the limits must be a mapping");
  }
  for (const key of ["lines", "orders", "zones"]) {
    if (!whole(limits[key])) {
      throw new Error("every limit must be a positive whole number");
    }
  }
  const lineCap = limits.lines as number;
  const orderCap = limits.orders as number;
  const zoneCap = limits.zones as number;
  if (!Array.isArray(orders)) throw new Error("the orders must be a list");

  const refs = new Set<string>();
  const parsed: Array<{ ref: string; lines: number; zones: string[] }> = [];
  for (const order of orders) {
    if (order === null || typeof order !== "object" || Array.isArray(order)) {
      throw new Error("an order must be a mapping");
    }
    const ref = (order as Record<string, unknown>).ref;
    if (typeof ref !== "string" || ref.length === 0) {
      throw new Error("an order needs a non-empty ref");
    }
    if (refs.has(ref)) throw new Error("two orders carry the same ref");
    refs.add(ref);
    const lines = (order as Record<string, unknown>).lines;
    if (!whole(lines)) throw new Error("lines must be a positive whole number");
    const zones = (order as Record<string, unknown>).zones;
    if (!Array.isArray(zones) || zones.length === 0) {
      throw new Error("an order needs a non-empty list of zones");
    }
    const kept: string[] = [];
    for (const zone of zones) {
      if (typeof zone !== "string" || !/^[a-f]$/.test(zone)) {
        throw new Error("a zone must be one letter from a to f");
      }
      if (kept.includes(zone)) throw new Error("an order repeats a zone");
      kept.push(zone);
    }
    parsed.push({ ref, lines: lines as number, zones: kept });
  }

  const waves: Wave[] = [];
  const refused: string[] = [];
  let open: Wave | null = null;
  for (const order of parsed) {
    if (order.lines > lineCap || order.zones.length > zoneCap) {
      refused.push(order.ref);
      continue;
    }
    if (open !== null) {
      const merged = new Set(open.zones);
      for (const zone of order.zones) merged.add(zone);
      const fits =
        open.lines + order.lines <= lineCap &&
        open.refs.length < orderCap &&
        merged.size <= zoneCap;
      if (fits) {
        open.refs.push(order.ref);
        open.lines += order.lines;
        open.zones = [...merged].sort();
        continue;
      }
    }
    open = {
      name: "w" + (waves.length + 1),
      refs: [order.ref],
      lines: order.lines,
      zones: [...order.zones].sort(),
    };
    waves.push(open);
  }

  return { waves, refused };
}
