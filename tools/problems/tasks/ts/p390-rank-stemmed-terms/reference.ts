export function rankStemmedTerms(
  passage: string,
  rules: unknown,
): Array<[string, number]> {
  if (typeof passage !== "string") {
    throw new Error("passage must be a string");
  }
  if (rules === null || typeof rules !== "object" || Array.isArray(rules)) {
    throw new Error("rules must be a mapping");
  }
  const spec = rules as Record<string, any>;
  if (!Array.isArray(spec.stops) || !Array.isArray(spec.endings)) {
    throw new Error("stops and endings must both be lists");
  }
  const lowercase = /^[a-z]+$/;
  for (const stop of spec.stops) {
    if (typeof stop !== "string" || !lowercase.test(stop)) {
      throw new Error("every stop word must be a non-empty run of lowercase letters");
    }
  }
  const endings: Array<[string, number]> = [];
  for (const entry of spec.endings) {
    if (!Array.isArray(entry) || entry.length !== 2) {
      throw new Error("every endings entry must be a pair of a tail and a floor");
    }
    const [tail, floor] = entry;
    if (typeof tail !== "string" || !lowercase.test(tail)) {
      throw new Error("every tail must be a non-empty run of lowercase letters");
    }
    if (!Number.isInteger(floor) || floor < 1) {
      throw new Error("every floor must be a whole number of at least one");
    }
    endings.push([tail, floor]);
  }
  const stops = new Set<string>(spec.stops);

  const counts = new Map<string, number>();
  for (const raw of passage.match(/[A-Za-z]+/g) ?? []) {
    let word = raw.toLowerCase();
    for (const [tail, floor] of endings) {
      if (word.endsWith(tail) && word.length - tail.length >= floor) {
        word = word.slice(0, word.length - tail.length);
        break;
      }
    }
    if (stops.has(word)) {
      continue;
    }
    counts.set(word, (counts.get(word) ?? 0) + 1);
  }

  const ranked: Array<[string, number]> = [...counts.entries()];
  ranked.sort((left, right) => {
    if (left[1] !== right[1]) {
      return right[1] - left[1];
    }
    return left[0] < right[0] ? -1 : left[0] > right[0] ? 1 : 0;
  });
  return ranked;
}
