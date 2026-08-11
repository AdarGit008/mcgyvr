/** Replay tile requests against a size-limited cache of fresh renders. */
export function tileRenders(requests: [number, string][], freshFor: number, size: number): [number, string][] {
  if (!Number.isInteger(freshFor) || freshFor < 1 || !Number.isInteger(size) || size < 1) {
    throw new Error("freshFor and size must be positive integers");
  }
  const held = new Map<string, number>();
  const renders: [number, string][] = [];
  for (const [tick, name] of requests) {
    const since = held.get(name);
    if (since !== undefined && tick < since + freshFor) {
      continue;
    }
    if (since === undefined && held.size === size) {
      let oldest = "";
      let oldestAt = Infinity;
      for (const [other, at] of held) {
        if (at < oldestAt || (at === oldestAt && other < oldest)) {
          oldest = other;
          oldestAt = at;
        }
      }
      held.delete(oldest);
    }
    held.set(name, tick);
    renders.push([tick, name]);
  }
  return renders;
}
