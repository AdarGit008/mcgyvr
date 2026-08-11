export function codeSum(code: string): number {
  const figures = "0123456789";
  let total = 0;
  for (const ch of code) {
    const at = figures.indexOf(ch);
    if (at >= 0) {
      total += at;
    }
  }
  return total;
}

/** The codes whose figure total divides evenly by three. */
export function goodCodes(codes: string[]): string[] {
  const kept: string[] = [];
  for (const code of codes) {
    if (codeSum(code) % 3 === 0) {
      kept.push(code);
    }
  }
  return kept;
}
