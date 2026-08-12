export function timeAdd(
  hour: number,
  minute: number,
  added: number,
): number[] {
  const total = (hour * 60 + minute + added) % (24 * 60);
  return [Math.floor(total / 60), total % 60];
}
