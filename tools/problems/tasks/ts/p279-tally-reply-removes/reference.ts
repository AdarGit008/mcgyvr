export function tallyReplyRemoves(links: string[][]): number[] {
  if (!Array.isArray(links) || links.length === 0) {
    throw new Error("the batch must hold at least one link");
  }
  const known = new Set<string>();
  for (const link of links) {
    if (!Array.isArray(link) || link.length !== 2) {
      throw new Error("a link is exactly two values");
    }
    for (const field of link) {
      if (typeof field !== "string") {
        throw new Error("a link field must be a string");
      }
    }
    if (link[0].length === 0) {
      throw new Error("a note needs an id");
    }
    if (known.has(link[0])) {
      throw new Error("an id is used twice");
    }
    known.add(link[0]);
  }

  const openers: string[] = [];
  const answersTo = new Map<string, string[]>();
  for (const [id, answers] of links) {
    if (answers.length === 0) {
      openers.push(id);
      continue;
    }
    if (!known.has(answers)) {
      throw new Error("an answers field names no note in the batch");
    }
    const kept = answersTo.get(answers);
    if (kept === undefined) {
      answersTo.set(answers, [id]);
    } else {
      kept.push(id);
    }
  }

  const counts: number[] = [];
  let standing = openers;
  let reached = 0;
  while (standing.length > 0) {
    counts.push(standing.length);
    reached += standing.length;
    const next: string[] = [];
    for (const id of standing) {
      for (const child of answersTo.get(id) ?? []) {
        next.push(child);
      }
    }
    standing = next;
  }
  if (reached !== links.length) {
    throw new Error("the answering runs in a circle");
  }
  return counts;
}
