export function flipOne(pair: string[]): string[] {
  return [pair[1], pair[0]];
}

export function flipAll(pairs: string[][]): string[][] {
  const flipped: string[][] = [];
  for (const pair of pairs) {
    flipped.push(flipOne(pair));
  }
  return flipped;
}
