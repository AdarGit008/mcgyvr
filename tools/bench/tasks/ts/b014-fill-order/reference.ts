export function fillOrder(
  sources: number[][],
  needed: number,
): { cost: number; taken: number[]; leftover: number[] } {
  if (!Number.isInteger(needed) || needed < 1) {
    throw new Error("needed must be a positive integer");
  }
  if (!Array.isArray(sources)) {
    throw new Error("sources must be a list");
  }
  let available = 0;
  for (const source of sources) {
    if (!Array.isArray(source) || source.length !== 2) {
      throw new Error("every source is a [cost, stock] pair");
    }
    const [unitCost, stock] = source;
    if (!Number.isInteger(unitCost) || unitCost < 1) {
      throw new Error("cost must be a positive integer");
    }
    if (!Number.isInteger(stock) || stock < 1) {
      throw new Error("stock must be a positive integer");
    }
    available += stock;
  }
  if (available < needed) {
    throw new Error("sources cannot cover the order");
  }
  const order = sources.map((_, index) => index);
  order.sort((a, b) => sources[a][0] - sources[b][0]);
  const taken = sources.map(() => 0);
  let cost = 0;
  let remaining = needed;
  for (const index of order) {
    if (remaining === 0) {
      break;
    }
    const [unitCost, stock] = sources[index];
    const draw = Math.min(stock, remaining);
    taken[index] = draw;
    cost += draw * unitCost;
    remaining -= draw;
  }
  const leftover = sources.map((source, index) => source[1] - taken[index]);
  return { cost, taken, leftover };
}
