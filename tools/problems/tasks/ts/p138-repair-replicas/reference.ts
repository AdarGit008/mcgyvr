export function repairReplicas(replicas: Array<Array<number | null>>): number[] {
  if (!Array.isArray(replicas) || replicas.length === 0) {
    throw new Error("the replica list must be non-empty");
  }
  const width = replicas[0].length;
  for (const replica of replicas) {
    if (!Array.isArray(replica) || replica.length !== width) {
      throw new Error("replica arrays differ in length");
    }
    for (const slot of replica) {
      if (slot !== null && !Number.isInteger(slot)) {
        throw new Error("a slot must hold an integer or null");
      }
    }
  }
  const rebuilt: number[] = [];
  for (let position = 0; position < width; position++) {
    const tally = new Map<number, number>();
    let surviving = 0;
    for (const replica of replicas) {
      const slot = replica[position];
      if (slot === null) {
        continue;
      }
      surviving += 1;
      tally.set(slot, (tally.get(slot) ?? 0) + 1);
    }
    if (surviving === 0) {
      throw new Error("a position is lost in every replica");
    }
    let winner: number | null = null;
    for (const [value, count] of tally) {
      if (count * 2 > surviving) {
        winner = value;
      }
    }
    if (winner === null) {
      throw new Error("no strict majority at some position");
    }
    rebuilt.push(winner);
  }
  return rebuilt;
}
