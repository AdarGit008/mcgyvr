/** Cent-exact money helpers for order totals. */

export function splitEvenly(totalCents: number, ways: number): number[] {
  if (!Number.isInteger(totalCents) || totalCents < 0) {
    throw new Error("total must be a non-negative integer of cents");
  }
  if (!Number.isInteger(ways) || ways <= 0) {
    throw new Error("ways must be a positive integer");
  }
  const base = Math.floor(totalCents / ways);
  const extra = totalCents - base * ways;
  const parts: number[] = [];
  for (let i = 0; i < ways; i++) {
    parts.push(i < extra ? base + 1 : base);
  }
  return parts;
}

export function applyBps(cents: number, bps: number): number {
  if (!Number.isInteger(cents) || cents < 0) {
    throw new Error("cents must be a non-negative integer");
  }
  if (!Number.isInteger(bps) || bps < 0) {
    throw new Error("bps must be a non-negative integer");
  }
  return Math.floor((cents * bps + 5000) / 10000);
}

export function sumParts(parts: number[]): number {
  let total = 0;
  for (const part of parts) {
    if (!Number.isInteger(part)) {
      throw new Error("parts must be integers");
    }
    total += part;
  }
  return total;
}
