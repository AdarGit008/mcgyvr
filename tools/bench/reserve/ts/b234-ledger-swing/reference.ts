export function ledgerSwing(balances: number[]): number {
  let widest = 0;
  for (let i = 1; i < balances.length; i += 1) {
    const swing = Math.abs(balances[i] - balances[i - 1]);
    if (swing > widest) {
      widest = swing;
    }
  }
  return widest;
}
