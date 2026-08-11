export function moveStock(opening: number, moves: number[]): number {
  let held = opening;
  for (const move of moves) {
    held += move;
    if (held < 0) {
      held = 0;
    }
  }
  return held;
}
