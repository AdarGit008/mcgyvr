export function payout(stake: number, odds: number): number {
  if (stake < 0) {
    throw new Error("a stake cannot be negative");
  }
  return stake * odds;
}

export function settleAll(
  bets: { stake: number; odds: number; won: boolean }[],
): number {
  let total = 0;
  for (const bet of bets) {
    if (bet.won) {
      total += payout(bet.stake, bet.odds);
    }
  }
  return total;
}
