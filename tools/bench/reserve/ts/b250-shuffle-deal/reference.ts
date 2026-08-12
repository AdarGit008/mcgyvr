export function shuffleDeal(cards: string[], hands: number): string[][] {
  if (hands === 0) {
    return [];
  }
  const dealt: string[][] = [];
  for (let i = 0; i < hands; i += 1) {
    dealt.push([]);
  }
  for (let i = 0; i < cards.length; i += 1) {
    dealt[i % hands].push(cards[i]);
  }
  return dealt;
}

export function dealCounts(dealt: string[][]): number[] {
  return dealt.map((hand) => hand.length);
}
