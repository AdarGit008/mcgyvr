function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function mapping(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function apportionLegCosts(
  legs: Record<string, unknown>[],
  travellers: Record<string, unknown>[],
): Record<string, unknown>[] {
  if (!Array.isArray(legs) || !Array.isArray(travellers)) {
    throw new Error("apportionLegCosts expects two lists");
  }
  if (legs.length === 0) {
    throw new Error("the trip has no legs");
  }
  if (travellers.length === 0) {
    throw new Error("the trip has no travellers");
  }

  const order = new Map<string, number>();
  const cost: number[] = [];
  const payer: string[] = [];
  for (const leg of legs) {
    if (!mapping(leg)) {
      throw new Error("a leg is not a mapping");
    }
    if (Object.keys(leg).sort().join(",") !== "cents,name,payer") {
      throw new Error("a leg carries exactly name, cents and payer");
    }
    const name = leg["name"];
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a leg name is not a non-empty string");
    }
    if (order.has(name)) {
      throw new Error("two legs share a name");
    }
    const cents = leg["cents"];
    if (!whole(cents) || Number(cents) < 0) {
      throw new Error("a leg's cents are not whole or fall below nought");
    }
    const paidBy = leg["payer"];
    if (typeof paidBy !== "string" || paidBy.length === 0) {
      throw new Error("a leg's payer is not a non-empty string");
    }
    order.set(name, cost.length);
    cost.push(Number(cents));
    payer.push(paidBy);
  }

  const joined = new Map<string, { from: number; to: number }>();
  for (const rider of travellers) {
    if (!mapping(rider)) {
      throw new Error("a traveller is not a mapping");
    }
    if (Object.keys(rider).sort().join(",") !== "joins,leaves,name") {
      throw new Error("a traveller carries exactly name, joins and leaves");
    }
    const name = rider["name"];
    if (typeof name !== "string" || name.length === 0) {
      throw new Error("a traveller name is not a non-empty string");
    }
    if (joined.has(name)) {
      throw new Error("two travellers share a name");
    }
    const joins = rider["joins"];
    const leaves = rider["leaves"];
    if (typeof joins !== "string" || !order.has(joins)) {
      throw new Error("a traveller joins at a leg the trip does not run");
    }
    if (typeof leaves !== "string" || !order.has(leaves)) {
      throw new Error("a traveller leaves at a leg the trip does not run");
    }
    const from = order.get(joins) ?? 0;
    const to = order.get(leaves) ?? 0;
    if (to < from) {
      throw new Error("a traveller leaves before joining");
    }
    joined.set(name, { from, to });
  }

  for (const who of payer) {
    if (!joined.has(who)) {
      throw new Error("a leg is paid by someone not on the trip");
    }
  }

  const names = [...joined.keys()].sort();
  const owes = new Map<string, number>();
  const paid = new Map<string, number>();
  for (const name of names) {
    owes.set(name, 0);
    paid.set(name, 0);
  }

  for (let index = 0; index < cost.length; index++) {
    const present = names.filter((name) => {
      const window = joined.get(name);
      return window !== undefined && window.from <= index && index <= window.to;
    });
    if (present.length === 0) {
      throw new Error("a leg carries nobody at all");
    }
    const each = Math.floor(cost[index] / present.length);
    let spare = cost[index] - each * present.length;
    for (const name of present) {
      const extra = spare > 0 ? 1 : 0;
      spare -= extra;
      owes.set(name, (owes.get(name) ?? 0) + each + extra);
    }
    paid.set(payer[index], (paid.get(payer[index]) ?? 0) + cost[index]);
  }

  return names.map((name) => ({
    name,
    owes: owes.get(name) ?? 0,
    paid: paid.get(name) ?? 0,
  }));
}
