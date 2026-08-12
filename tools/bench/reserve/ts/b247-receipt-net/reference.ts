export function receiptNet(
  lines: { amount: number; voided: boolean }[],
): number {
  let net = 0;
  for (const line of lines) {
    if (!line.voided) {
      net += line.amount;
    }
  }
  return net;
}
