export function tallyHallRows(hall: string[]): string[] {
  if (!Array.isArray(hall) || hall.length === 0) {
    throw new Error("the hall must be a non-empty list of tiers");
  }
  let width = -1;
  for (const tier of hall) {
    if (typeof tier !== "string" || tier.length === 0) {
      throw new Error("every tier must be a non-empty string");
    }
    if (width === -1) {
      width = tier.length;
    } else if (tier.length !== width) {
      throw new Error("the tiers differ in width");
    }
    for (const ch of tier) {
      if (ch !== "x" && ch !== "o" && ch !== "=") {
        throw new Error("stray character in the hall: " + ch);
      }
    }
  }

  const lines: string[] = [];
  let heldAll = 0;
  let openAll = 0;
  let widest = 0;
  let widestOpen = -1;
  for (let at = 0; at < hall.length; at += 1) {
    let held = 0;
    let open = 0;
    for (const ch of hall[at]) {
      if (ch === "x") held += 1;
      if (ch === "o") open += 1;
    }
    if (held + open === 0) {
      throw new Error("tier " + at + " offers no chair whatsoever");
    }
    lines.push("tier" + at + " held=" + held + " open=" + open);
    heldAll += held;
    openAll += open;
    if (open > widestOpen) {
      widestOpen = open;
      widest = at;
    }
  }
  lines.push("hall held=" + heldAll + " open=" + openAll + " widest=tier" + widest);
  return lines;
}
