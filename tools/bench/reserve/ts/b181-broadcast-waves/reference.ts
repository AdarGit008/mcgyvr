/** Report a bulletin's spread through the desks, one wave per hop. */
export function broadcastWaves(links: string[], start: string): string {
  const onward: Record<string, string[]> = {};
  for (const link of links) {
    const parts = link.split(">");
    if (parts.length !== 2 || parts[0] === "" || parts[1] === "") {
      throw new Error("a link must be written sender>receiver");
    }
    (onward[parts[0]] ??= []).push(parts[1]);
  }
  const held = new Set<string>([start]);
  const lines: string[] = [];
  let wave = [start];
  while (wave.length > 0) {
    lines.push(wave.join(", "));
    const reached: string[] = [];
    for (const desk of wave) {
      for (const target of onward[desk] ?? []) {
        if (!held.has(target)) {
          held.add(target);
          reached.push(target);
        }
      }
    }
    reached.sort();
    wave = reached;
  }
  return lines.join("\n");
}
