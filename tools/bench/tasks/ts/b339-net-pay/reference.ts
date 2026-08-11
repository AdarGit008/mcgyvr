/** Gross pay less a percentage and then a flat fee. */
export function netPay(gross: number, rate: number, fee: number): number {
  const afterRate = gross - Math.floor((gross * rate) / 100);
  return Math.max(afterRate - fee, 0);
}
