export function rollupTotals(
  nodes: Record<string, { value: number; parent: string }>,
): Record<string, number> {
  const ids = Object.keys(nodes);
  const roots: string[] = [];
  const children = new Map<string, string[]>();
  for (const id of ids) {
    const up = nodes[id].parent;
    if (up === "") {
      roots.push(id);
    } else if (!(up in nodes)) {
      throw new Error(`unknown parent ${up}`);
    } else {
      const kids = children.get(up) ?? [];
      kids.push(id);
      children.set(up, kids);
    }
  }
  if (roots.length !== 1) {
    throw new Error("the hierarchy needs exactly one root");
  }
  const totals: Record<string, number> = {};
  let visited = 0;
  const subtree = (id: string): number => {
    visited += 1;
    let total = nodes[id].value;
    for (const kid of children.get(id) ?? []) {
      total += subtree(kid);
    }
    totals[id] = total;
    return total;
  };
  subtree(roots[0]);
  if (visited !== ids.length) {
    throw new Error("some nodes cannot be reached from the root");
  }
  return totals;
}
