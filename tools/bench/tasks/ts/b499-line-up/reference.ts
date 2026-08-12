export function lineUp(links: Record<string, string>, start: string): string[] {
  const line: string[] = [start];
  let at = start;
  while (at in links) {
    at = links[at];
    if (line.includes(at)) {
      throw new Error("the links run in a circle");
    }
    line.push(at);
  }
  return line;
}
