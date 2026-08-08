export function applyCyclePower(panel: number[], rounds: number): number[] {
  if (!Array.isArray(panel) || panel.length === 0) {
    throw new Error("the panel must be a non-empty list");
  }
  if (typeof rounds !== "number" || !Number.isInteger(rounds) || rounds < 0) {
    throw new Error("rounds must be a whole number of zero or more");
  }
  const size = panel.length;
  const named = new Set<number>();
  for (const entry of panel) {
    if (typeof entry !== "number" || !Number.isInteger(entry)) {
      throw new Error("every entry must be a whole number");
    }
    if (entry < 0 || entry >= size) {
      throw new Error("entry names a slot the panel does not have");
    }
    if (named.has(entry)) {
      throw new Error("a slot is named twice");
    }
    named.add(entry);
  }
  const settled = new Array(size).fill(false);
  const moved = new Array(size).fill(0);
  for (let start = 0; start < size; start++) {
    if (settled[start]) continue;
    const ring: number[] = [];
    let at = start;
    while (!settled[at]) {
      settled[at] = true;
      ring.push(at);
      at = panel[at];
    }
    const slide = rounds % ring.length;
    for (let i = 0; i < ring.length; i++) {
      moved[ring[i]] = ring[(i + slide) % ring.length];
    }
  }
  return moved;
}
