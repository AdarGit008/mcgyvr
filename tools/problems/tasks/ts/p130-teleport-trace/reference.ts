export function traceTeleports(pads: number[], start: number): number[] {
  const n = pads.length;
  if (n === 0) {
    throw new Error("empty hall");
  }
  for (const p of pads) {
    if (!Number.isInteger(p) || p < 0 || p >= n) {
      throw new Error("destination outside the hall");
    }
  }
  if (!Number.isInteger(start) || start < 0 || start >= n) {
    throw new Error("start outside the hall");
  }
  const seenAt = new Map<number, number>();
  let at = start;
  let rides = 0;
  while (!seenAt.has(at)) {
    seenAt.set(at, rides);
    at = pads[at];
    rides += 1;
  }
  const entry = seenAt.get(at) as number;
  return [entry, rides - entry, at];
}
