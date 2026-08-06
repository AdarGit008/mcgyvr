/** Kahn's algorithm, always taking the smallest ready node. */
export function topoSort(n: number, edges: [number, number][]): number[] {
  if (!Number.isInteger(n) || n < 0) {
    throw new Error("n must be a nonnegative integer");
  }
  const adjacency: number[][] = Array.from({ length: n }, () => []);
  const indegree: number[] = new Array(n).fill(0);
  for (const [u, v] of edges) {
    if (!Number.isInteger(u) || !Number.isInteger(v) || u < 0 || v < 0 || u >= n || v >= n) {
      throw new Error("edge endpoints must be integers in [0, n)");
    }
    adjacency[u].push(v);
    indegree[v] += 1;
  }
  const ready = new Set<number>();
  for (let node = 0; node < n; node++) {
    if (indegree[node] === 0) {
      ready.add(node);
    }
  }
  const order: number[] = [];
  while (ready.size > 0) {
    const next = Math.min(...ready);
    ready.delete(next);
    order.push(next);
    for (const v of adjacency[next]) {
      indegree[v] -= 1;
      if (indegree[v] === 0) {
        ready.add(v);
      }
    }
  }
  if (order.length < n) {
    throw new Error("graph contains a cycle");
  }
  return order;
}
