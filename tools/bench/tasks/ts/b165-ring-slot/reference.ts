/** The slot of a ring recorder holding the k-th oldest surviving reading. */
export function ringSlot(capacity: number, writes: number, k: number): number {
  if (!Number.isInteger(capacity) || capacity < 1) {
    throw new Error("capacity must be a positive integer");
  }
  if (!Number.isInteger(writes) || writes < 0) {
    throw new Error("writes must be a non-negative integer");
  }
  if (!Number.isInteger(k) || k < 0) {
    throw new Error("k must be a non-negative integer");
  }
  const survivors = Math.min(writes, capacity);
  if (k >= survivors) {
    throw new Error("no survivor at that rank");
  }
  return (writes - survivors + k) % capacity;
}
