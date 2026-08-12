/** What is owed across a ledger of charges and payments. */
export function owedTotal(entries: number[]): number {
  let total = 0;
  for (const entry of entries) {
    total += entry;
  }
  if (total < 0) {
    throw new Error("the total cannot fall below nothing");
  }
  return total;
}
