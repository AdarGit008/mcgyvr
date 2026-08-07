function sharedOpening(run: string[]): string {
  let opening = run[0];
  for (const word of run) {
    let i = 0;
    while (i < opening.length && i < word.length && opening[i] === word[i]) {
      i += 1;
    }
    opening = opening.slice(0, i);
  }
  return opening;
}

function byOpeningLetter(run: string[]): string[][] {
  const buckets = new Map<string, string[]>();
  for (const word of run) {
    const head = word[0];
    const bucket = buckets.get(head);
    if (bucket === undefined) {
      buckets.set(head, [word]);
    } else {
      bucket.push(word);
    }
  }
  return [...buckets.keys()].sort().map((head) => buckets.get(head));
}

function squeeze(run: string[]): string {
  if (run.length === 1) {
    return run[0];
  }
  const opening = sharedOpening(run);
  const tails = run.map((word) => word.slice(opening.length));
  const parts: string[] = [];
  if (tails.some((tail) => tail === "")) {
    parts.push("-");
  }
  for (const bucket of byOpeningLetter(tails.filter((tail) => tail !== ""))) {
    parts.push(squeeze(bucket));
  }
  return `${opening}(${parts.join("|")})`;
}

export function foldWordTrie(words: string[]): string {
  if (!Array.isArray(words) || words.length === 0) {
    throw new Error("words must be a list holding at least one word");
  }
  const seen = new Set<string>();
  for (const word of words) {
    if (typeof word !== "string") {
      throw new Error("every word must be a string");
    }
    if (word.length === 0) {
      throw new Error("an empty word cannot be squeezed");
    }
    if (!/^[a-z]+$/.test(word)) {
      throw new Error(`${word} carries something other than small letters`);
    }
    if (seen.has(word)) {
      throw new Error(`${word} turns up twice`);
    }
    seen.add(word);
  }
  const sorted = [...words].sort();
  return byOpeningLetter(sorted).map(squeeze).join("|");
}
