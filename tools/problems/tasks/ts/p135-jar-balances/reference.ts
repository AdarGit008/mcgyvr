export function jarBalances(
  topup: number,
  lid: number,
  outflows: number[],
): number[] {
  if (!Number.isInteger(topup) || topup < 0) {
    throw new Error("topup must be a non-negative integer");
  }
  if (!Number.isInteger(lid) || lid < 0) {
    throw new Error("lid must be a non-negative integer");
  }
  if (!Array.isArray(outflows)) {
    throw new Error("outflows must be a list");
  }
  const closes: number[] = [];
  let held = 0;
  for (const outflow of outflows) {
    if (!Number.isInteger(outflow) || outflow < 0) {
      throw new Error("an outflow must be a non-negative integer");
    }
    held += topup;
    if (outflow > held) {
      throw new Error("the jar cannot cover this outflow");
    }
    held -= outflow;
    if (held > lid) {
      held = lid;
    }
    closes.push(held);
  }
  return closes;
}
