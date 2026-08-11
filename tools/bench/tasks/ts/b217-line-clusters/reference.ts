/** Group a tram operator's stops into the clusters its track segments join. */
export function lineClusters(stops: string[], links: [string, string][]): string[][] {
  const home: Record<string, string> = {};
  for (const stop of stops) {
    home[stop] = stop;
  }
  const root = (stop: string): string => {
    while (home[stop] !== stop) {
      stop = home[stop];
    }
    return stop;
  };
  for (const [from, to] of links) {
    home[root(from)] = root(to);
  }
  const groups: Record<string, string[]> = {};
  for (const stop of stops) {
    const key = root(stop);
    (groups[key] ??= []).push(stop);
  }
  const clusters = Object.values(groups).map((members) => [...members].sort());
  clusters.sort((left, right) => (left[0] < right[0] ? -1 : 1));
  return clusters;
}
