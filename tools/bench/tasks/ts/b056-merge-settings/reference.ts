/** Three-way merge of flat settings: base against ours and theirs, per key. */
export function mergeSettings(
  base: Record<string, string>,
  ours: Record<string, string>,
  theirs: Record<string, string>,
): Record<string, string> {
  for (const side of [base, ours, theirs]) {
    if (typeof side !== "object" || side === null || Array.isArray(side)) {
      throw new Error("each side must be a plain settings object");
    }
    for (const value of Object.values(side)) {
      if (typeof value !== "string") {
        throw new Error("settings values must be strings");
      }
    }
  }
  const merged: Record<string, string> = {};
  for (const key of Object.keys({ ...base, ...ours, ...theirs })) {
    const stem = base[key];
    const own = ours[key];
    const other = theirs[key];
    let kept: string | undefined;
    if (own === other) kept = own;
    else if (own === stem) kept = other;
    else if (other === stem) kept = own;
    else throw new Error("conflicting edits to " + key);
    if (kept !== undefined) merged[key] = kept;
  }
  return merged;
}
