export function quarterHour(minutes: number): number {
  if (minutes < 0) {
    throw new Error("minutes cannot be negative");
  }
  return Math.floor(minutes / 15) * 15;
}
