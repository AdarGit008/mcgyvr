export function liveCount(neighbours: boolean[]): number {
  let living = 0;
  for (const neighbour of neighbours) {
    if (neighbour) {
      living += 1;
    }
  }
  return living;
}

export function liveNext(alive: boolean, neighbours: boolean[]): boolean {
  const living = liveCount(neighbours);
  if (alive) {
    return living === 2 || living === 3;
  }
  return living === 3;
}
