/** Stable multi-key sort: decorate with index, compare key by key. */
export function sortBy(
  rows: Record<string, unknown>[],
  keys: { key: string; dir: "asc" | "desc" }[],
): Record<string, unknown>[] {
  const rank = (v: unknown): number =>
    typeof v === "number" ? 0 : typeof v === "string" ? 1 : 2;
  const compareValues = (x: unknown, y: unknown): number => {
    const rx = rank(x);
    const ry = rank(y);
    if (rx !== ry) return rx - ry;
    if (rx === 0) return (x as number) - (y as number);
    if (rx === 1) {
      const sx = x as string;
      const sy = y as string;
      return sx < sy ? -1 : sx > sy ? 1 : 0;
    }
    return 0;
  };
  const decorated = rows.map((row, index) => ({ row, index }));
  decorated.sort((a, b) => {
    for (const { key, dir } of keys) {
      const c = compareValues(a.row[key], b.row[key]);
      if (c !== 0) return dir === "desc" ? -c : c;
    }
    return a.index - b.index;
  });
  return decorated.map((d) => d.row);
}
