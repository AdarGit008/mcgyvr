/** Smallest-first Kahn ordering with duplicate-edge deduplication. */
export function topoOrder(n: number, edges: [number, number][]): number[] {
  const adjacency: Set<number>[] = [];
  for (let v = 0; v < n; v++) adjacency.push(new Set());
  const indegree: number[] = new Array(n).fill(0);
  for (const [u, v] of edges) {
    if (!adjacency[u].has(v)) {
      adjacency[u].add(v);
      indegree[v] += 1;
    }
  }
  const placed: boolean[] = new Array(n).fill(false);
  const out: number[] = [];
  for (let step = 0; step < n; step++) {
    let pick = -1;
    for (let v = 0; v < n; v++) {
      if (!placed[v] && indegree[v] === 0) {
        pick = v;
        break;
      }
    }
    if (pick === -1) throw new Error("the graph contains a cycle");
    placed[pick] = true;
    out.push(pick);
    for (const w of adjacency[pick]) indegree[w] -= 1;
  }
  return out;
}
