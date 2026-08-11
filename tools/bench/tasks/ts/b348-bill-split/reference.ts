export function billSplit(total: number, diners: number): number[] {
  const share = Math.floor(total / diners);
  const shares: number[] = [];
  for (let i = 0; i < diners; i += 1) {
    shares.push(share);
  }
  shares[0] += total - share * diners;
  return shares;
}
