/** Turn an archive's article titles into slugs no two articles share. */
export function slugTitles(titles: string[]): string[] {
  if (!Array.isArray(titles)) {
    throw new Error("slugTitles expects a list of titles");
  }
  const seen: Record<string, number> = {};
  const slugs: string[] = [];
  for (const title of titles) {
    if (typeof title !== "string") {
      throw new Error("every title must be a string");
    }
    let base = "";
    for (const ch of title.toLowerCase()) {
      const plain = (ch >= "a" && ch <= "z") || (ch >= "0" && ch <= "9");
      if (plain) base += ch;
      else if (base !== "" && !base.endsWith("-")) base += "-";
    }
    while (base.endsWith("-")) base = base.slice(0, -1);
    if (base === "") {
      throw new Error("a title must hold a letter or a digit");
    }
    const claim = (seen[base] ?? 0) + 1;
    seen[base] = claim;
    slugs.push(claim === 1 ? base : base + "-" + claim);
  }
  return slugs;
}
