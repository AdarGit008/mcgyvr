export function stopZone(stop: string): number {
  if (stop === "central" || stop === "market") {
    return 1;
  }
  if (stop === "harbour") {
    return 2;
  }
  return 3;
}

/** Two hundred cents for every different zone the journey touches. */
export function zoneFare(stops: string[]): number {
  const touched = new Set<number>();
  for (const stop of stops) {
    touched.add(stopZone(stop));
  }
  return touched.size * 200;
}
