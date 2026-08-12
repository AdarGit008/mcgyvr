/** Order release tags oldest first, candidates before their release. */
export function orderReleases(tags: string[]): string[] {
  if (!Array.isArray(tags)) {
    throw new Error("orderReleases expects a list of tags");
  }
  const form = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-rc\.([1-9]\d*))?$/;
  const seen = new Set<string>();
  const keyed: { key: number[]; tag: string }[] = [];
  for (const tag of tags) {
    if (typeof tag !== "string") {
      throw new Error("every tag must be a string");
    }
    const match = form.exec(tag);
    if (match === null) {
      throw new Error("malformed release tag: " + tag);
    }
    if (seen.has(tag)) {
      throw new Error("tag appears twice: " + tag);
    }
    seen.add(tag);
    const finished = match[4] === undefined;
    keyed.push({
      key: [
        Number(match[1]),
        Number(match[2]),
        Number(match[3]),
        finished ? 1 : 0,
        finished ? 0 : Number(match[4]),
      ],
      tag,
    });
  }
  keyed.sort((a, b) => {
    for (let i = 0; i < 5; i++) {
      if (a.key[i] !== b.key[i]) {
        return a.key[i] - b.key[i];
      }
    }
    return 0;
  });
  return keyed.map((entry) => entry.tag);
}
