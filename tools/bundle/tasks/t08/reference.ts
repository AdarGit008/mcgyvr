/** Order nodes so every [from, to] edge is respected, ties by input order. */
export function topologicalSort(
  nodes: readonly string[],
  edges: readonly (readonly [string, string])[],
): string[] {
  const known = new Set(nodes);
  const incoming = new Map<string, number>(nodes.map((node) => [node, 0]));
  const outgoing = new Map<string, string[]>(nodes.map((node) => [node, []]));
  for (const [from, to] of edges) {
    if (!known.has(from) || !known.has(to)) {
      throw new Error(`edge names an unknown node: [${from}, ${to}]`);
    }
    (outgoing.get(from) as string[]).push(to);
    incoming.set(to, (incoming.get(to) as number) + 1);
  }
  const order: string[] = [];
  const ready = nodes.filter((node) => incoming.get(node) === 0);
  while (ready.length > 0) {
    const node = ready.shift() as string;
    order.push(node);
    for (const next of outgoing.get(node) as string[]) {
      const remaining = (incoming.get(next) as number) - 1;
      incoming.set(next, remaining);
      if (remaining === 0) {
        // Insert by input order so ties resolve the way the contract states.
        const at = ready.findIndex((other) => nodes.indexOf(other) > nodes.indexOf(next));
        if (at === -1) {
          ready.push(next);
        } else {
          ready.splice(at, 0, next);
        }
      }
    }
  }
  if (order.length !== nodes.length) {
    const stuck = nodes.filter((node) => !order.includes(node));
    throw new Error(`cycle among: ${stuck.join(", ")}`);
  }
  return order;
}
