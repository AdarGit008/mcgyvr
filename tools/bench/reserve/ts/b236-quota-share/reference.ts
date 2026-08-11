export function quotaShare(budget: number, weights: number[]): number[] {
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  if (total === 0) {
    return weights.map(() => 0);
  }
  const shares = weights.map((w) => Math.floor((budget * w) / total));
  let best = 0;
  for (let i = 1; i < weights.length; i += 1) {
    if (weights[i] > weights[best]) {
      best = i;
    }
  }
  shares[best] += budget - shares.reduce((sum, share) => sum + share, 0);
  return shares;
}
