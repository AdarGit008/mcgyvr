export function placeDonations(
  requests: Array<{
    id: string;
    kind: string;
    from: number;
    to: number;
    urgent: boolean;
  }>,
  lots: Array<{ id: string; kind: string; day: number }>,
): Array<[string, string]> {
  const requestIds = new Set<string>();
  for (const request of requests) {
    if (requestIds.has(request.id)) {
      throw new Error("repeated request id");
    }
    requestIds.add(request.id);
    if (!Number.isInteger(request.from) || !Number.isInteger(request.to)) {
      throw new Error("from and to must be integers");
    }
    if (request.from > request.to) {
      throw new Error("a span with from greater than to is malformed");
    }
  }
  const lotIds = new Set<string>();
  const open = requests.map(() => true);
  const placed: Array<[string, string]> = [];
  for (const lot of lots) {
    if (lotIds.has(lot.id)) {
      throw new Error("repeated lot id");
    }
    lotIds.add(lot.id);
    if (!Number.isInteger(lot.day)) {
      throw new Error("day must be an integer");
    }
    let best = -1;
    for (let i = 0; i < requests.length; i++) {
      if (!open[i]) {
        continue;
      }
      const request = requests[i];
      const fits =
        lot.day >= request.from &&
        lot.day <= request.to &&
        (lot.kind === "ANY" || lot.kind === request.kind);
      if (!fits) {
        continue;
      }
      if (best === -1) {
        best = i;
        continue;
      }
      const leader = requests[best];
      const wins =
        (request.urgent && !leader.urgent) ||
        (request.urgent === leader.urgent && request.to < leader.to);
      if (wins) {
        best = i;
      }
    }
    if (best !== -1) {
      open[best] = false;
      placed.push([lot.id, requests[best].id]);
    }
  }
  return placed;
}
