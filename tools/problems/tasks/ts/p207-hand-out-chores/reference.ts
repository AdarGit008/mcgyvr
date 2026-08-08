export function handOutChores(
  chores: string[],
  crew: string[],
): Record<string, string[]> {
  if (!Array.isArray(chores)) {
    throw new Error("the chore board must be a list");
  }
  const listed = new Set<string>();
  for (const chore of chores) {
    if (typeof chore !== "string" || chore.length === 0) {
      throw new Error("every chore must be a non-empty string");
    }
    if (listed.has(chore)) {
      throw new Error("the board lists " + chore + " twice");
    }
    listed.add(chore);
  }
  if (!Array.isArray(crew) || crew.length === 0) {
    throw new Error("the crew must be a list with somebody on it");
  }
  const share: Record<string, string[]> = {};
  for (const who of crew) {
    if (typeof who !== "string" || who.length === 0) {
      throw new Error("every crew name must be a non-empty string");
    }
    if (Object.prototype.hasOwnProperty.call(share, who)) {
      throw new Error("two crew members share the name " + who);
    }
    share[who] = [];
  }

  let marker = 0;
  for (const chore of chores) {
    share[crew[marker]].push(chore);
    marker = (marker + chore.length) % crew.length;
  }
  return share;
}
