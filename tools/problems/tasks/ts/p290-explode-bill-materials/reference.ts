type Use = { part: string; per: number };
type Assembly = { part: string; uses: Use[] };

function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function explodeBillOfMaterials(
  parts: Assembly[],
  root: string,
  batch: number,
): { part: string; count: number }[] {
  if (!Array.isArray(parts)) {
    throw new Error("parts must be a list");
  }
  if (typeof root !== "string" || root.length === 0) {
    throw new Error("root must be a non-empty string");
  }
  if (!whole(batch) || batch < 1) {
    throw new Error("batch must be an integer of at least 1");
  }

  const index = new Map<string, Use[]>();
  for (const entry of parts) {
    if (entry === null || typeof entry !== "object") {
      throw new Error("a parts entry must be a record");
    }
    if (typeof entry.part !== "string" || entry.part.length === 0) {
      throw new Error("a part name must be a non-empty string");
    }
    if (index.has(entry.part)) {
      throw new Error("parts names the same part twice: " + entry.part);
    }
    if (!Array.isArray(entry.uses) || entry.uses.length === 0) {
      throw new Error("uses must be a non-empty list: " + entry.part);
    }
    const here = new Set<string>();
    for (const use of entry.uses) {
      if (use === null || typeof use !== "object") {
        throw new Error("a uses entry must be a record");
      }
      if (typeof use.part !== "string" || use.part.length === 0) {
        throw new Error("a sub-part name must be a non-empty string");
      }
      if (here.has(use.part)) {
        throw new Error(entry.part + " names " + use.part + " twice");
      }
      here.add(use.part);
      if (!whole(use.per) || use.per < 1) {
        throw new Error("per must be an integer of at least 1: " + use.part);
      }
    }
    index.set(entry.part, entry.uses);
  }

  const totals = new Map<string, number>();
  const chain = new Set<string>();

  const explode = (name: string, many: number): void => {
    const uses = index.get(name);
    if (uses === undefined) {
      totals.set(name, (totals.get(name) ?? 0) + many);
      return;
    }
    if (chain.has(name)) {
      throw new Error("the build loops through " + name);
    }
    chain.add(name);
    for (const use of uses) {
      explode(use.part, many * use.per);
    }
    chain.delete(name);
  };

  explode(root, batch);

  const names = [...totals.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  return names.map((part) => ({ part, count: totals.get(part) as number }));
}
