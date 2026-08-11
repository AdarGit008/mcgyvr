/** Spend charges against named quota buckets, refusing what will not fit. */
function whyRefused(cap: [number, number] | undefined, left: number, amount: number): string {
  if (cap === undefined) {
    return "unknown";
  }
  if (amount > cap[1]) {
    return "single";
  }
  return amount > left ? "cap" : "";
}

export function applyCharges(caps: Record<string, [number, number]>, charges: [string, string, number][]): { left: Record<string, number>; refused: [string, string][] } {
  const left: Record<string, number> = Object.fromEntries(Object.keys(caps).map((name) => [name, caps[name][0]]));
  const refused: [string, string][] = [];
  for (const [id, bucket, amount] of charges) {
    if (!Number.isInteger(amount) || amount < 1) {
      throw new Error("a charge amount must be a positive whole number");
    }
    const reason = whyRefused(caps[bucket], left[bucket], amount);
    if (reason === "") {
      left[bucket] -= amount;
    } else {
      refused.push([id, reason]);
    }
  }
  return { left, refused };
}
