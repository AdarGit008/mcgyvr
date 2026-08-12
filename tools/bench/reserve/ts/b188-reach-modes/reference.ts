/** Every mode a control panel can still reach by walking its signals. */
export function reachableModes(
  table: Record<string, Record<string, string>>,
  start: string,
): string[] {
  const mapping = typeof table === "object" && table !== null && !Array.isArray(table);
  if (!mapping) {
    throw new Error("reachableModes expects a table of modes");
  }
  if (!Object.prototype.hasOwnProperty.call(table, start)) {
    throw new Error("the starting mode is not keyed by the table");
  }
  const found = new Set<string>();
  // Walk out of a mode only the first time it is entered, so cycles settle.
  function walk(mode: string): void {
    if (found.has(mode)) return;
    found.add(mode);
    const signals = table[mode];
    if (signals === undefined) return;
    for (const signal of Object.keys(signals)) {
      walk(signals[signal]);
    }
  }
  walk(start);
  return [...found].sort();
}
