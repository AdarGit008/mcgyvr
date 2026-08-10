/** The cheapest set of travel passes covering every trip day. */

function validatePlan(
  tripDays: number[],
  passes: { span: number; cost: number }[],
): void {
  for (const day of tripDays) {
    if (!Number.isInteger(day) || day < 1) {
      throw new Error("trip days must be positive integers");
    }
  }
  for (let i = 1; i < tripDays.length; i += 1) {
    if (tripDays[i] <= tripDays[i - 1]) {
      throw new Error("trip days must be strictly increasing");
    }
  }
  if (passes.length === 0) {
    throw new Error("at least one pass kind is required");
  }
  for (const pass of passes) {
    if (!Number.isInteger(pass.span) || pass.span < 1) {
      throw new Error("pass span must be a positive integer");
    }
    if (!Number.isInteger(pass.cost) || pass.cost < 0) {
      throw new Error("pass cost must be a non-negative integer");
    }
  }
}

export function cheapestPassPlan(
  tripDays: number[],
  passes: { span: number; cost: number }[],
): { total: number; purchases: number[][] } {
  validatePlan(tripDays, passes);
  const count = tripDays.length;
  const best: number[] = new Array(count + 1).fill(0);
  const choice: number[] = new Array(count).fill(0);
  for (let i = count - 1; i >= 0; i -= 1) {
    best[i] = Infinity;
    for (let p = 0; p < passes.length; p += 1) {
      const expiry = tripDays[i] + passes[p].span;
      let next = i;
      while (next < count && tripDays[next] < expiry) {
        next += 1;
      }
      const candidate = passes[p].cost + best[next];
      if (candidate < best[i]) {
        best[i] = candidate;
        choice[i] = p;
      }
    }
  }
  const purchases: number[][] = [];
  let at = 0;
  while (at < count) {
    const bought = passes[choice[at]];
    purchases.push([tripDays[at], bought.span]);
    const expiry = tripDays[at] + bought.span;
    while (at < count && tripDays[at] < expiry) {
      at += 1;
    }
  }
  return { total: best[0], purchases };
}
