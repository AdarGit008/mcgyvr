export function scoreScale(
  mark: number,
  wasOutOf: number,
  nowOutOf: number,
): number {
  if (wasOutOf <= 0) {
    return 0;
  }
  const scaled = Math.floor((mark * nowOutOf) / wasOutOf);
  return scaled > nowOutOf ? nowOutOf : scaled;
}
