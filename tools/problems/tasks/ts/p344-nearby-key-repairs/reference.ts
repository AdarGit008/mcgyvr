function isLowerWord(value: unknown): boolean {
  return (
    typeof value === "string" && value.length > 0 && /^[a-z]+$/.test(value)
  );
}

export function nearbyKeyRepairs(
  word: string,
  lexicon: string[],
  neighbours: Record<string, string>,
): string[] {
  if (!isLowerWord(word)) {
    throw new Error("the typed word must be a non-empty lowercase string");
  }
  if (!Array.isArray(lexicon)) {
    throw new Error("the dictionary must be a list");
  }
  for (const entry of lexicon) {
    if (!isLowerWord(entry)) {
      throw new Error("every dictionary word must be a lowercase string");
    }
  }
  if (
    typeof neighbours !== "object" ||
    neighbours === null ||
    Array.isArray(neighbours)
  ) {
    throw new Error("the neighbour table must be a plain mapping");
  }
  for (const [key, touching] of Object.entries(neighbours)) {
    if (!/^[a-z]$/.test(key)) {
      throw new Error("a neighbour table key must be one lowercase letter");
    }
    if (typeof touching !== "string" || !/^[a-z]*$/.test(touching)) {
      throw new Error("a neighbour entry must be a lowercase string");
    }
    if (touching.includes(key)) {
      throw new Error("a key may not neighbour itself");
    }
    if (new Set(touching).size !== touching.length) {
      throw new Error("a neighbour entry may not repeat a key");
    }
  }

  const known = new Set(lexicon);
  if (known.has(word)) {
    return [word];
  }
  const found: { place: number; order: number; guess: string }[] = [];
  for (let place = 0; place < word.length; place += 1) {
    const touching = neighbours[word[place]];
    if (typeof touching !== "string") {
      continue;
    }
    for (let order = 0; order < touching.length; order += 1) {
      const guess =
        word.slice(0, place) + touching[order] + word.slice(place + 1);
      if (known.has(guess)) {
        found.push({ place, order, guess });
      }
    }
  }
  found.sort((a, b) => (a.place !== b.place ? b.place - a.place : a.order - b.order));
  return found.slice(0, 3).map((row) => row.guess);
}
