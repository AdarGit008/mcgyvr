/** What is left after an amount is taken from stock. */
export function takeDown(held: number, amount: number): number {
  if (amount > held) {
    throw new Error("more than is held cannot be taken");
  }
  return held - amount;
}
