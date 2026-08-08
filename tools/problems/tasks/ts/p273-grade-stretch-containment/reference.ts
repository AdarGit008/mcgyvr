export function gradeContainment(
  source: string[],
  draft: string[],
  span: number,
): number {
  if (!Number.isInteger(span) || span <= 0) {
    throw new Error("span must be a positive whole number");
  }
  const vet = (words: string[], label: string): void => {
    if (!Array.isArray(words)) {
      throw new Error(label + " must be a list");
    }
    for (const word of words) {
      if (typeof word !== "string" || word.length === 0) {
        throw new Error(label + " holds something that is not a word");
      }
    }
  };
  vet(source, "source");
  vet(draft, "draft");
  if (draft.length < span) {
    throw new Error("the draft holds fewer words than span");
  }

  const tally = new Map<string, number>();
  for (let i = 0; i + span <= source.length; i++) {
    const stretch = source.slice(i, i + span).join(" ");
    tally.set(stretch, (tally.get(stretch) ?? 0) + 1);
  }

  let matched = 0;
  let total = 0;
  for (let i = 0; i + span <= draft.length; i++) {
    total += 1;
    const stretch = draft.slice(i, i + span).join(" ");
    const unspent = tally.get(stretch) ?? 0;
    if (unspent > 0) {
      tally.set(stretch, unspent - 1);
      matched += 1;
    }
  }
  return Math.floor((matched * 1000) / total);
}
