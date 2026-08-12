/** Convert along a measure ladder declared by unordered bigger-to-smaller rules. */
export function ladderConvert(rules: [string, string, number][], amount: number, source: string, goal: string): number {
  if (!Number.isInteger(amount) || amount < 0) {
    throw new Error("amount must be a non-negative integer");
  }
  const down = new Map<string, [string, number]>();
  const smalls = new Set<string>();
  for (const [big, small, factor] of rules) {
    if (!Number.isInteger(factor) || factor < 2) {
      throw new Error("factor must be an integer of at least 2");
    }
    if (down.has(big) || smalls.has(small)) {
      throw new Error("unit sits twice on the same side");
    }
    down.set(big, [small, factor]);
    smalls.add(small);
  }
  const heads = [...down.keys()].filter((unit) => !smalls.has(unit));
  if (heads.length !== 1) {
    throw new Error("rules must form one single ladder");
  }
  const order = [heads[0]];
  const factors: number[] = [];
  let link = down.get(heads[0]);
  while (link !== undefined) {
    order.push(link[0]);
    factors.push(link[1]);
    link = down.get(link[0]);
  }
  if (factors.length !== down.size) {
    throw new Error("rules must form one single ladder");
  }
  const si = order.indexOf(source);
  const gi = order.indexOf(goal);
  if (si === -1 || gi === -1) {
    throw new Error("unit not named by the ladder");
  }
  let step = 1;
  for (let i = Math.min(si, gi); i < Math.max(si, gi); i++) step *= factors[i];
  if (si <= gi) return amount * step;
  if (amount % step !== 0) {
    throw new Error("upward conversion does not come out whole");
  }
  return amount / step;
}
