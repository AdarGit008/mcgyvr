export function stitchTables(
  left: Array<Record<string, unknown>>,
  right: Array<Record<string, unknown>>,
  key: string,
  mode: string,
): Array<Record<string, unknown>> {
  if (mode !== "inner" && mode !== "left") {
    throw new Error("unknown mode");
  }
  const keyOf = (row: Record<string, unknown>): string => {
    const value = row[key];
    if (typeof value !== "string") {
      throw new Error("every record needs the key column as a string");
    }
    return value;
  };
  const byKey = new Map<string, Record<string, unknown>>();
  const rightCols = new Set<string>();
  for (const row of right) {
    const value = keyOf(row);
    if (byKey.has(value)) {
      throw new Error("a right-table key value repeats");
    }
    byKey.set(value, row);
    for (const name of Object.keys(row)) {
      if (name !== key) rightCols.add(name);
    }
  }
  const leftKeys: string[] = [];
  const leftCols = new Set<string>();
  for (const row of left) {
    leftKeys.push(keyOf(row));
    for (const name of Object.keys(row)) {
      if (name !== key) leftCols.add(name);
    }
  }
  for (const name of rightCols) {
    if (leftCols.has(name)) {
      throw new Error("the tables share a non-key column: " + name);
    }
  }
  const stitched: Array<Record<string, unknown>> = [];
  left.forEach((row, index) => {
    const partner = byKey.get(leftKeys[index]);
    if (partner === undefined && mode === "inner") return;
    const merged: Record<string, unknown> = { ...row };
    if (partner === undefined) {
      for (const name of rightCols) merged[name] = null;
    } else {
      for (const name of Object.keys(partner)) {
        if (name !== key) merged[name] = partner[name];
      }
    }
    stitched.push(merged);
  });
  return stitched;
}
