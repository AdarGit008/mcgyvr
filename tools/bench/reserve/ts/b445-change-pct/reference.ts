/** The change from an old value to a new one, as a percentage of the old. */
export function changePct(old: number, fresh: number): number {
  if (old === 0) {
    return 0;
  }
  return Math.floor(((fresh - old) * 100) / old);
}
