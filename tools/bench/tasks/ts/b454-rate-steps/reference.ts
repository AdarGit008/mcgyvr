export function stepRate(
  amount: number,
  fixed: number,
  percent: number,
): number {
  return fixed + Math.floor((amount * percent) / 100);
}

export function rateSteps(
  amounts: number[],
  fixed: number,
  percent: number,
): number[] {
  const charges: number[] = [];
  for (const amount of amounts) {
    charges.push(stepRate(amount, fixed, percent));
  }
  return charges;
}
