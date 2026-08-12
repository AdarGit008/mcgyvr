export function kindWeight(kind: string): number {
  if (kind === "steel") {
    return 10;
  }
  if (kind === "wood") {
    return 4;
  }
  return 1;
}

/** The kind carrying the greatest weight once counted together. */
export function topLoad(kinds: string[]): string {
  const totals: Record<string, number> = {};
  const arrived: string[] = [];
  for (const kind of kinds) {
    if (!(kind in totals)) {
      totals[kind] = 0;
      arrived.push(kind);
    }
    totals[kind] += kindWeight(kind);
  }
  let named = "";
  let greatest = 0;
  for (const kind of arrived) {
    if (totals[kind] > greatest) {
      named = kind;
      greatest = totals[kind];
    }
  }
  return named;
}
