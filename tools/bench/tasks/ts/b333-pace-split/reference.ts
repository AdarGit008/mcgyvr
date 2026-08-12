export function paceOf(seconds: number, kilometres: number): number {
  if (kilometres <= 0) {
    throw new Error("a leg must cover ground");
  }
  return Math.floor(seconds / kilometres);
}

export function paceList(
  legs: { seconds: number; kilometres: number }[],
): number[] {
  return legs.map((leg) => paceOf(leg.seconds, leg.kilometres));
}
