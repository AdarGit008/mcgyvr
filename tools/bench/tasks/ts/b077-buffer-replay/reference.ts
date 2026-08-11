export function replayBuffer(
  ops: string[],
  capacity: number,
): { held: string[]; taken: string[] } {
  if (!Number.isInteger(capacity) || capacity <= 0) {
    throw new Error("capacity must be a positive integer");
  }
  const held: string[] = [];
  const taken: string[] = [];
  for (const op of ops) {
    if (op === "take") {
      if (held.length === 0) {
        throw new Error("take on an empty buffer");
      }
      taken.push(held.shift() as string);
    } else if (op.startsWith("add:")) {
      if (held.length === capacity) {
        throw new Error("buffer is full");
      }
      held.push(op.slice(4));
    } else {
      throw new Error("unknown operation: " + op);
    }
  }
  return { held, taken };
}
