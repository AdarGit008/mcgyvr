export function siftDownRun(heap: number[], start: number): number[][] {
  if (!Array.isArray(heap) || heap.length === 0) {
    throw new Error("siftDownRun expects a non-empty array");
  }
  for (const value of heap) {
    if (typeof value !== "number" || !Number.isInteger(value)) {
      throw new Error("every entry must be a whole number");
    }
  }
  if (
    typeof start !== "number" ||
    !Number.isInteger(start) ||
    start < 0 ||
    start >= heap.length
  ) {
    throw new Error("start slot is outside the array");
  }
  const array = [...heap];
  const trail: number[] = [start];
  let slot = start;
  for (;;) {
    const left = 2 * slot + 1;
    const right = left + 1;
    if (left >= array.length) {
      break;
    }
    let pick = left;
    if (right < array.length && array[right] < array[left]) {
      pick = right;
    }
    if (array[pick] >= array[slot]) {
      break;
    }
    const held = array[slot];
    array[slot] = array[pick];
    array[pick] = held;
    slot = pick;
    trail.push(slot);
  }
  return [array, trail];
}
