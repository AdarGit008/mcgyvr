export function daysFor(size: number, rate: number): number {
  if (rate <= 0) {
    throw new Error("a rate must be positive");
  }
  return Math.ceil(size / rate);
}

export function planDays(sizes: number[], rate: number): number[] {
  const days: number[] = [];
  for (const size of sizes) {
    days.push(daysFor(size, rate));
  }
  return days;
}
