/** Deal a deck's cards round-robin into a fixed number of piles. */
export function dealRounds(deck: string, hands: number): string[] {
  if (typeof deck !== "string") {
    throw new Error("dealRounds expects a string deck");
  }
  if (!Number.isInteger(hands) || hands < 1) {
    throw new Error("hands must be a whole number of at least one");
  }
  const piles: string[] = new Array(hands).fill("");
  for (let i = 0; i < deck.length; i++) {
    piles[i % hands] += deck[i];
  }
  return piles;
}
