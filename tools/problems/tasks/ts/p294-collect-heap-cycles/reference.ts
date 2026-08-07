type Cell = { id: string; refs: string[]; finalizer: boolean };
type Report = { finalized: string[]; collected: string[] };

export function collectHeapCycles(heap: Cell[], held: string[][]): Report[] {
  if (!Array.isArray(heap)) {
    throw new Error("collectHeapCycles expects a heap list");
  }
  if (!Array.isArray(held)) {
    throw new Error("collectHeapCycles expects a list of held-id lists");
  }
  const order: string[] = [];
  const cells = new Map<string, Cell>();
  for (const cell of heap) {
    if (cell === null || typeof cell !== "object") {
      throw new Error("every heap entry must be a cell");
    }
    if (typeof cell.id !== "string") {
      throw new Error("a cell needs a string id");
    }
    if (!Array.isArray(cell.refs) || typeof cell.finalizer !== "boolean") {
      throw new Error("a cell needs a refs list and a boolean finalizer: " + cell.id);
    }
    if (cells.has(cell.id)) {
      throw new Error("two cells carry the id " + cell.id);
    }
    cells.set(cell.id, cell);
    order.push(cell.id);
  }
  for (const cell of heap) {
    for (const ref of cell.refs) {
      if (!cells.has(ref)) {
        throw new Error("ref names no cell: " + ref);
      }
    }
  }

  const present = new Set<string>(order);

  function reach(seeds: string[]): Set<string> {
    const painted = new Set<string>();
    const queue: string[] = [];
    for (const seed of seeds) {
      if (present.has(seed) && !painted.has(seed)) {
        painted.add(seed);
        queue.push(seed);
      }
    }
    while (queue.length > 0) {
      const here = queue.shift();
      for (const ref of cells.get(here).refs) {
        if (present.has(ref) && !painted.has(ref)) {
          painted.add(ref);
          queue.push(ref);
        }
      }
    }
    return painted;
  }

  const burnt = new Set<string>();
  const reports: Report[] = [];
  for (const roots of held) {
    if (!Array.isArray(roots)) {
      throw new Error("every collection needs a held-id list");
    }
    for (const id of roots) {
      if (typeof id !== "string" || !cells.has(id)) {
        throw new Error("held id names no cell: " + String(id));
      }
      if (!present.has(id)) {
        throw new Error("held id was already swept: " + id);
      }
    }
    const live = reach(roots);
    const doomed = order.filter((id) => present.has(id) && !live.has(id));
    const finalized = doomed.filter(
      (id) => cells.get(id).finalizer && !burnt.has(id),
    );
    for (const id of finalized) {
      burnt.add(id);
    }
    const spared = reach(finalized);
    const collected = doomed.filter((id) => !spared.has(id));
    for (const id of collected) {
      present.delete(id);
    }
    reports.push({ finalized, collected });
  }
  return reports;
}
