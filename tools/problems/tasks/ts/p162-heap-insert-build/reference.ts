export function buildMinHeapByInsertion(values: number[]): number[] {
  if (!Array.isArray(values)) {
    throw new Error("buildMinHeapByInsertion expects a list");
  }
  for (const value of values) {
    if (typeof value !== "number" || !Number.isInteger(value)) {
      throw new Error("every entry must be a whole number");
    }
  }
  const heap: number[] = [];
  for (const value of values) {
    heap.push(value);
    let slot = heap.length - 1;
    while (slot > 0) {
      const parent = Math.floor((slot - 1) / 2);
      if (heap[parent] <= heap[slot]) {
        break;
      }
      const held = heap[parent];
      heap[parent] = heap[slot];
      heap[slot] = held;
      slot = parent;
    }
  }
  return heap;
}
