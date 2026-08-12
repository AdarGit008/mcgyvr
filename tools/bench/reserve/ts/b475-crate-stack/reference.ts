export function crateHeight(kind: string): number {
  if (kind === "tall") {
    return 5;
  }
  if (kind === "short") {
    return 2;
  }
  return 3;
}

/** The kinds that fit below a ceiling, in the order given. */
export function crateStack(kinds: string[], ceiling: number): string[] {
  const kept: string[] = [];
  let piled = 0;
  for (const kind of kinds) {
    const raised = piled + crateHeight(kind);
    if (raised > ceiling) {
      return kept;
    }
    piled = raised;
    kept.push(kind);
  }
  return kept;
}
