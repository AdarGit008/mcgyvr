/** The snapshots to load to rebuild one wanted image. */
export function orderSnapshotLoad(archive: any[], wanted: string): any {
  if (!Array.isArray(archive)) {
    throw new Error("the archive must be a list");
  }
  const byName = new Map<string, any>();
  for (const entry of archive) {
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) {
      throw new Error("each snapshot is a record");
    }
    if (!("name" in entry) || !("parent" in entry)) {
      throw new Error("a snapshot needs both name and parent");
    }
    if (typeof entry.name !== "string" || entry.name === "") {
      throw new Error("name must be a non-empty string");
    }
    if (typeof entry.parent !== "string") {
      throw new Error("parent must be a string");
    }
    if (byName.has(entry.name)) {
      throw new Error("two snapshots share a name");
    }
    byName.set(entry.name, entry);
  }
  if (typeof wanted !== "string" || wanted === "") {
    throw new Error("the wanted snapshot must be a non-empty string");
  }
  const order: string[] = [];
  const seen = new Set<string>();
  let at = wanted;
  for (;;) {
    if (!byName.has(at)) {
      return { found: "no", order: [], why: "unknown" };
    }
    if (seen.has(at)) {
      return { found: "no", order: [], why: "cycle" };
    }
    seen.add(at);
    order.push(at);
    const parent = byName.get(at).parent;
    if (parent === "") {
      order.reverse();
      return { found: "yes", order, why: "" };
    }
    at = parent;
  }
}
