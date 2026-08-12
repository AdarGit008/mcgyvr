export function lockerGap(used: number[]): number {
  const taken = new Set(used);
  let locker = 1;
  while (taken.has(locker)) {
    locker += 1;
  }
  return locker;
}
