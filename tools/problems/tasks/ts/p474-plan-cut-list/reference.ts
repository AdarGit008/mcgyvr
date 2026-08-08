function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function planCutList(
  bars: number[],
  orders: Record<string, unknown>[],
  kerf: number,
  keep: number,
): { layout: number[][]; offcuts: number[]; scrap: number; short: number[] } {
  if (!Array.isArray(bars)) {
    throw new Error("planCutList expects a list of bars");
  }
  if (!Array.isArray(orders)) {
    throw new Error("the orders are not a list");
  }
  if (!whole(kerf) || kerf < 0) {
    throw new Error("the kerf is not whole or falls below nought");
  }
  if (!whole(keep) || keep < 0) {
    throw new Error("the keep is not whole or falls below nought");
  }
  for (const bar of bars) {
    if (!whole(bar) || bar < 1) {
      throw new Error("a bar is not whole or falls below one");
    }
  }

  const wanted: number[] = [];
  const named = new Set<number>();
  for (const order of orders) {
    if (typeof order !== "object" || order === null || Array.isArray(order)) {
      throw new Error("an order is not a mapping");
    }
    if (Object.keys(order).sort().join(",") !== "count,length") {
      throw new Error("an order's keys are not exactly length and count");
    }
    const length = order["length"];
    if (!whole(length) || (length as number) < 1) {
      throw new Error("a length is not whole or falls below one");
    }
    if (named.has(length as number)) {
      throw new Error("a length is named by two orders");
    }
    named.add(length as number);
    const count = order["count"];
    if (!whole(count) || (count as number) < 1) {
      throw new Error("a count is not whole or falls below one");
    }
    for (let made = 0; made < (count as number); made++) {
      wanted.push(length as number);
    }
  }
  wanted.sort((left, right) => right - left);

  const stillOn = bars.slice();
  const layout: number[][] = bars.map(() => []);
  const short: number[] = [];
  for (const piece of wanted) {
    let cut = false;
    for (let index = 0; index < stillOn.length; index++) {
      if (piece <= stillOn[index]) {
        layout[index].push(piece);
        const rest = stillOn[index] - piece - kerf;
        stillOn[index] = rest > 0 ? rest : 0;
        cut = true;
        break;
      }
    }
    if (!cut) {
      short.push(piece);
    }
  }

  const offcuts: number[] = [];
  let scrap = 0;
  for (const rest of stillOn) {
    if (rest <= 0) {
      continue;
    }
    if (rest >= keep) {
      offcuts.push(rest);
    } else {
      scrap += rest;
    }
  }

  return { layout, offcuts, scrap, short };
}
