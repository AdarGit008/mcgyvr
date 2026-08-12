export function stepBack(moves: string): number {
  let here = 0;
  let furthest = 0;
  for (const move of moves) {
    if (move === "F") {
      here += 1;
    } else if (move === "B") {
      here -= 1;
    }
    if (here > furthest) {
      furthest = here;
    }
  }
  return furthest;
}
