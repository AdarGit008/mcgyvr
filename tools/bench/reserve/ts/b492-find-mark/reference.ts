export function findMark(ordered: number[], mark: number): number {
  let low = 0;
  let high = ordered.length - 1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    if (ordered[mid] === mark) {
      return mid;
    }
    if (ordered[mid] < mark) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return -1;
}
