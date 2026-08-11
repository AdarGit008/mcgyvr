export function servedBy(queue: string[], turn: number): string {
  if (queue.length === 0) {
    throw new Error("a queue needs somebody in it");
  }
  return queue[turn % queue.length];
}

/** Who is served on each turn, the queue coming round again. */
export function queueRound(queue: string[], turns: number): string[] {
  const served: string[] = [];
  for (let turn = 0; turn < turns; turn += 1) {
    served.push(servedBy(queue, turn));
  }
  return served;
}
