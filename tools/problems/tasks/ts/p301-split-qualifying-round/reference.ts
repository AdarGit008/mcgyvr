export function splitQualifyingRound(
  entrants: string[],
): { direct: string[]; qualifying: string[][] } {
  if (!Array.isArray(entrants)) {
    throw new Error("splitQualifyingRound expects a list of entrants");
  }
  if (entrants.length < 2) {
    throw new Error("a field needs at least two entrants");
  }
  const seen = new Set<string>();
  for (const name of entrants) {
    if (typeof name !== "string") {
      throw new Error("an entrant name is a string");
    }
    if (seen.has(name)) {
      throw new Error("listed twice: " + name);
    }
    seen.add(name);
  }
  let draw = 1;
  while (draw * 2 <= entrants.length) {
    draw *= 2;
  }
  const surplus = entrants.length - draw;
  const walking = entrants.length - 2 * surplus;
  const direct = entrants.slice(0, walking);
  const group = entrants.slice(walking);
  const qualifying: string[][] = [];
  for (let at = 0; at < surplus; at++) {
    qualifying.push([group[at], group[group.length - 1 - at]]);
  }
  return { direct, qualifying };
}
