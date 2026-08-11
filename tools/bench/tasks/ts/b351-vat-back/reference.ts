export function vatBack(gross: number, rate: number): number {
  if (rate === 0) {
    return gross;
  }
  return Math.floor((gross * 100) / (100 + rate));
}
