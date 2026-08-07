export function allocateCents(total: number, weights: number[]): number[] {
  if (typeof total !== "number" || !Number.isInteger(total) || total < 0) {
    throw new Error("total must be a non-negative integer of cents");
  }
  if (!Array.isArray(weights) || weights.length === 0) {
    throw new Error("weights must be a non-empty list");
  }
  for (const w of weights) {
    if (typeof w !== "number" || !Number.isInteger(w) || w <= 0) {
      throw new Error("every weight must be a positive integer");
    }
  }
  const weightSum = weights.reduce((a, b) => a + b, 0);
  const shares = weights.map((w) => Math.floor((total * w) / weightSum));
  const remainders = weights.map((w) => (total * w) % weightSum);
  let leftover = total - shares.reduce((a, b) => a + b, 0);
  const order = weights
    .map((_, i) => i)
    .sort((a, b) => remainders[b] - remainders[a] || a - b);
  for (let k = 0; k < leftover; k++) {
    shares[order[k]] += 1;
  }
  return shares;
}
