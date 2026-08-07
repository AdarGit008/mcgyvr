export function mergeThreeWay(
  base: Record<string, string>,
  ours: Record<string, string>,
  theirs: Record<string, string>,
): { merged: Record<string, string>; conflicts: string[] } {
  for (const side of [base, ours, theirs]) {
    if (
      typeof side !== "object" ||
      side === null ||
      Array.isArray(side) ||
      Object.values(side).some((v) => typeof v !== "string")
    ) {
      throw new Error("each argument must be a mapping of strings to strings");
    }
  }
  const merged: Record<string, string> = {};
  const conflicts: string[] = [];
  const keys = new Set([
    ...Object.keys(base),
    ...Object.keys(ours),
    ...Object.keys(theirs),
  ]);
  for (const key of [...keys].sort()) {
    const b = Object.hasOwn(base, key) ? base[key] : undefined;
    const o = Object.hasOwn(ours, key) ? ours[key] : undefined;
    const t = Object.hasOwn(theirs, key) ? theirs[key] : undefined;
    let pick: string | undefined;
    if (o === b && t === b) {
      pick = b;
    } else if (o === b) {
      pick = t;
    } else if (t === b) {
      pick = o;
    } else if (o === t) {
      pick = o;
    } else {
      conflicts.push(key);
      pick = b;
    }
    if (pick !== undefined) {
      merged[key] = pick;
    }
  }
  return { merged, conflicts };
}
