/** The printed lots at each limit once the flow has worked the ladder. */
type Ticket = {
  ref: string;
  way: string;
  limit: number;
  lots: number;
  at: number;
};

function readTicket(raw: unknown, at: number, refs: Set<string>): Ticket {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("a ticket must be a mapping");
  }
  const row = raw as Record<string, unknown>;
  const ref = row.ref;
  if (typeof ref !== "string" || ref.length === 0) {
    throw new Error("a ticket needs a non-empty ref");
  }
  if (refs.has(ref)) {
    throw new Error("two tickets carry the same ref");
  }
  refs.add(ref);
  const way = row.way;
  if (way !== "buy" && way !== "sell") {
    throw new Error("a way must be buy or sell");
  }
  const limit = row.limit;
  const lots = row.lots;
  for (const value of [limit, lots]) {
    if (typeof value !== "number" || !Number.isInteger(value) || value < 1) {
      throw new Error("limit and lots must be positive whole numbers");
    }
  }
  return { ref, way, limit: limit as number, lots: lots as number, at };
}

export function foldTapePrints(
  opening: Array<Record<string, unknown>>,
  flow: Array<Record<string, unknown>>,
): Record<string, unknown> {
  if (!Array.isArray(opening) || !Array.isArray(flow)) {
    throw new Error("both arguments must be lists");
  }
  const refs = new Set<string>();
  let ladder = opening.map((row, at) => readTicket(row, at, refs));
  const prints = new Map<number, number>();
  let at = ladder.length;

  for (const raw of flow) {
    const taker = readTicket(raw, at, refs);
    at += 1;
    const buying = taker.way === "buy";
    const far = ladder.filter(
      (ticket) =>
        ticket.way !== taker.way &&
        (buying ? ticket.limit <= taker.limit : ticket.limit >= taker.limit),
    );
    far.sort((a, b) =>
      a.limit === b.limit
        ? a.at - b.at
        : buying
          ? a.limit - b.limit
          : b.limit - a.limit,
    );
    let left = taker.lots;
    for (const ticket of far) {
      if (left === 0) {
        break;
      }
      const lots = Math.min(left, ticket.lots);
      prints.set(ticket.limit, (prints.get(ticket.limit) ?? 0) + lots);
      ticket.lots -= lots;
      left -= lots;
    }
    ladder = ladder.filter((ticket) => ticket.lots > 0);
    if (left > 0) {
      ladder.push({ ...taker, lots: left });
    }
  }

  const rows = [...prints.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([limit, lots]) => ({ limit, lots }));
  let rest = 0;
  for (const ticket of ladder) {
    rest += ticket.lots;
  }
  return { prints: rows, left: rest };
}
