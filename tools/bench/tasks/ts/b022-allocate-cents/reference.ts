/** Fixed-point money helpers: parse, format, and allocate integer cents. */

export function parseAmount(text: string): number {
  if (typeof text !== "string") {
    throw new Error("amount must be a string");
  }
  const match = /^(\d+)(?:\.(\d{2}))?$/.exec(text);
  if (match === null) {
    throw new Error(`malformed amount: ${text}`);
  }
  const whole = Number(match[1]);
  const cents = match[2] === undefined ? 0 : Number(match[2]);
  return whole * 100 + cents;
}

export function formatAmount(cents: number): string {
  if (!Number.isInteger(cents) || cents < 0) {
    throw new Error("cents must be a non-negative integer");
  }
  const whole = Math.floor(cents / 100);
  const rest = String(cents % 100).padStart(2, "0");
  return `${whole}.${rest}`;
}

export function allocateCents(totalCents: number, weights: number[]): number[] {
  if (!Number.isInteger(totalCents) || totalCents < 0) {
    throw new Error("total must be a non-negative integer");
  }
  if (weights.length === 0) {
    throw new Error("weights must not be empty");
  }
  let sum = 0;
  for (const weight of weights) {
    if (!Number.isInteger(weight) || weight < 0) {
      throw new Error("weights must be non-negative integers");
    }
    sum += weight;
  }
  if (sum === 0) {
    throw new Error("weights must not sum to zero");
  }
  const shares: number[] = [];
  const remainders: number[] = [];
  let assigned = 0;
  for (const weight of weights) {
    const exact = totalCents * weight;
    const share = Math.floor(exact / sum);
    shares.push(share);
    remainders.push(exact % sum);
    assigned += share;
  }
  let leftover = totalCents - assigned;
  const order = remainders
    .map((remainder, index) => [remainder, index])
    .sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  for (const [, index] of order) {
    if (leftover === 0) {
      break;
    }
    shares[index] += 1;
    leftover -= 1;
  }
  return shares;
}
