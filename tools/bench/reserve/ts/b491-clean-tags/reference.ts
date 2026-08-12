export function tagOk(tag: string): boolean {
  if (tag.length === 0) {
    return false;
  }
  const allowed = "abcdefghijklmnopqrstuvwxyz-";
  for (const ch of tag.toLowerCase()) {
    if (!allowed.includes(ch)) {
      return false;
    }
  }
  return true;
}

/** The tags that may be kept, lowered, without repeats. */
export function cleanTags(tags: string[]): string[] {
  const kept: string[] = [];
  for (const tag of tags) {
    if (!tagOk(tag)) {
      continue;
    }
    const lowered = tag.toLowerCase();
    if (!kept.includes(lowered)) {
      kept.push(lowered);
    }
  }
  return kept;
}
