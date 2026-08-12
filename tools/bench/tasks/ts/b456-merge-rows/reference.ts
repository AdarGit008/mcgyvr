export function rowKeys(row: Record<string, string>): string[] {
  return Object.keys(row);
}

/** One row laid over another, the row above winning. */
export function mergeRows(
  under: Record<string, string>,
  over: Record<string, string>,
): Record<string, string> {
  const merged: Record<string, string> = { ...under };
  for (const key of rowKeys(over)) {
    merged[key] = over[key];
  }
  return merged;
}
