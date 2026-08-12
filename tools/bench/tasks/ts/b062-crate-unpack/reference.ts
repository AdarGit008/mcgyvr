/** Unpack a nested crate of item names into a flat picking list. */

export function unpackCrates(crate: unknown[]): string[] {
  const names: string[] = [];
  for (const entry of crate) {
    if (Array.isArray(entry)) {
      names.push(...unpackCrates(entry));
    } else if (typeof entry === "string" && entry !== "") {
      names.push(entry);
    } else {
      throw new Error("crate entries are item names or nested crates");
    }
  }
  return names;
}

export function crateDepth(crate: unknown[]): number {
  let depth = 1;
  for (const entry of crate) {
    if (Array.isArray(entry)) {
      const inner = 1 + crateDepth(entry);
      if (inner > depth) {
        depth = inner;
      }
    }
  }
  return depth;
}
