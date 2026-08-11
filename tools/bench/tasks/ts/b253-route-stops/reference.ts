export function routeStops(route: string): string[] {
  if (route.trim().length === 0) {
    return [];
  }
  return route.split(">").map((stop) => stop.trim());
}

export function routeHops(route: string): number {
  const stops = routeStops(route);
  return stops.length === 0 ? 0 : stops.length - 1;
}
