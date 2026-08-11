export function splitCents(total: number, weights: number[]): number[] {
  if (!Number.isInteger(total)) throw new Error("total must be whole cents");
  if (total < 0) throw new Error("total may not be negative");
  if (!Array.isArray(weights) || weights.length === 0) throw new Error("weights must be a non-empty list");
  if (!weights.every((w) => Number.isInteger(w) && w > 0)) throw new Error("a weight is a positive whole number");
  const whole = weights.reduce((a, b) => a + b, 0);
  const parts = weights.map((w) => Math.floor((total * w) / whole));
  const order = weights.map((w, i) => i);
  order.sort((a, b) => ((total * weights[b]) % whole) - ((total * weights[a]) % whole) || a - b);
  let over = total - parts.reduce((a, b) => a + b, 0);
  for (const i of order) {
    if (over > 0) { parts[i] += 1; over -= 1; }
  }
  return parts;
}
