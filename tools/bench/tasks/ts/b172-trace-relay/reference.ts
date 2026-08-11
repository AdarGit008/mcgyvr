export function traceRelay(links: Record<string, string>, start: string): string[] {
  if (links === null || typeof links !== "object" || Array.isArray(links)) throw new Error("links must be a mapping");
  if (!(start in links)) throw new Error("start is not a post");
  const route: string[] = [];
  let post = start;
  while (post !== "") {
    if (route.includes(post)) throw new Error("the watch comes back on itself");
    if (!(post in links)) throw new Error("a handoff names a post links does not hold");
    route.push(post);
    post = links[post];
  }
  return route;
}
