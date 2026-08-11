export function tillFloat(amount: number, coins: number[]): number[] {
  const counts: number[] = [];
  let left = amount;
  for (const coin of coins) {
    counts.push(Math.floor(left / coin));
    left %= coin;
  }
  return counts;
}
