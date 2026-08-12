export function swipeDedupe(swipes: string[]): string[] {
  const kept: string[] = [];
  for (const swipe of swipes) {
    if (kept.length === 0 || kept[kept.length - 1] !== swipe) {
      kept.push(swipe);
    }
  }
  return kept;
}
