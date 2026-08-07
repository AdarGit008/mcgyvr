export function levelStrip(
  readings: number[],
  low: number,
  high: number,
  ramp: string,
): string {
  if (ramp.length === 0) {
    throw new Error("empty ramp");
  }
  if (high <= low) {
    throw new Error("span must rise");
  }
  const n = ramp.length;
  let out = "";
  for (const r of readings) {
    let index = Math.floor(((r - low) * n) / (high - low));
    if (index < 0) {
      index = 0;
    }
    if (index >= n) {
      index = n - 1;
    }
    out += ramp[index];
  }
  return out;
}
