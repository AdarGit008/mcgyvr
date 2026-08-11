export function interestAdd(
  amount: number,
  rate: number,
  years: number,
): number {
  const interest = Math.floor((amount * rate * years) / 100);
  return amount + interest;
}
