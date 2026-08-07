export function runBufferedLine(
  capacities: number[],
  buffers: number[],
  ticks: number,
): { made: number; left: number[] } {
  const posInt = (v: unknown): boolean =>
    typeof v === "number" && Number.isInteger(v) && v >= 1;
  if (!Array.isArray(capacities) || capacities.length === 0) {
    throw new Error("no stations");
  }
  if (!Array.isArray(buffers) || buffers.length !== capacities.length - 1) {
    throw new Error("buffer count mismatch");
  }
  for (const c of capacities) {
    if (!posInt(c)) {
      throw new Error("bad per-tick limit");
    }
  }
  for (const b of buffers) {
    if (!posInt(b)) {
      throw new Error("bad buffer size");
    }
  }
  if (typeof ticks !== "number" || !Number.isInteger(ticks) || ticks < 0) {
    throw new Error("bad tick count");
  }
  const n = capacities.length;
  const held = buffers.map(() => 0);
  let made = 0;
  for (let t = 0; t < ticks; t++) {
    for (let i = n - 1; i >= 0; i--) {
      const inbound = i === 0 ? Infinity : held[i - 1];
      const room = i === n - 1 ? Infinity : buffers[i] - held[i];
      const moved = Math.min(capacities[i], inbound, room);
      if (i > 0) {
        held[i - 1] -= moved;
      }
      if (i < n - 1) {
        held[i] += moved;
      } else {
        made += moved;
      }
    }
  }
  return { made, left: held };
}
