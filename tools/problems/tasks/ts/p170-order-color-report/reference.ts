export function orderColorReport(
  neighbours: number[][],
  visitOrder: number[],
): number[][] {
  if (!Array.isArray(neighbours) || neighbours.length === 0) {
    throw new Error("there must be at least one transmitter");
  }
  const count = neighbours.length;
  for (let node = 0; node < count; node++) {
    const clashes = neighbours[node];
    if (!Array.isArray(clashes)) {
      throw new Error("each transmitter needs a list of clashes");
    }
    for (const other of clashes) {
      if (typeof other !== "number" || !Number.isInteger(other)) {
        throw new Error("a clash must name a transmitter number");
      }
      if (other < 0 || other >= count) {
        throw new Error("a clash names a transmitter that does not exist");
      }
      if (other === node) {
        throw new Error("a transmitter cannot clash with itself");
      }
      if (!neighbours[other].includes(node)) {
        throw new Error("a clash is recorded on one side only");
      }
    }
  }
  if (!Array.isArray(visitOrder) || visitOrder.length !== count) {
    throw new Error("the walking sequence must be every transmitter exactly once");
  }
  const seen = new Set<number>();
  for (const node of visitOrder) {
    if (typeof node !== "number" || node < 0 || node >= count || seen.has(node)) {
      throw new Error("the walking sequence must be every transmitter exactly once");
    }
    seen.add(node);
  }

  const channel: number[] = new Array(count).fill(-1);
  for (const node of visitOrder) {
    const taken = new Set<number>();
    for (const other of neighbours[node]) {
      if (channel[other] >= 0) {
        taken.add(channel[other]);
      }
    }
    let pick = 0;
    while (taken.has(pick)) {
      pick += 1;
    }
    channel[node] = pick;
  }
  const distinct = new Set(channel);
  return [channel, [distinct.size]];
}
