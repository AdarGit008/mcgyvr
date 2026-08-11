export function dayNext(today: number, wanted: number): number {
  let gap = wanted - today;
  if (gap <= 0) {
    gap += 7;
  }
  return gap;
}
