export function remainingFor(used: Record<string, number>, key: string, allowance: number): number {
  return allowance - (key in used ? used[key] : 0);
}

export function meterDraws(
  draws: [string, number][],
  allowance: number,
): { used: Record<string, number>; denied: number[] } {
  if (!Number.isInteger(allowance) || allowance <= 0) {
    throw new Error("allowance must be a positive integer");
  }
  const used: Record<string, number> = {};
  const denied: number[] = [];
  draws.forEach((draw, index) => {
    const [key, units] = draw;
    if (typeof key !== "string" || key.length === 0) {
      throw new Error("key must be a non-empty string");
    }
    if (!Number.isInteger(units) || units <= 0) {
      throw new Error("units must be a positive integer");
    }
    if (!(key in used)) used[key] = 0;
    if (units <= remainingFor(used, key, allowance)) used[key] += units;
    else denied.push(index);
  });
  return { used, denied };
}
