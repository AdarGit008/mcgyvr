function wordish(character: string | undefined): boolean {
  return character !== undefined && /[A-Za-z0-9]/.test(character);
}

export function tightenNotePhrases(
  text: string,
  book: Record<string, string>,
): string {
  if (typeof text !== "string") {
    throw new Error("tightenNotePhrases expects a string of text");
  }
  if (typeof book !== "object" || book === null || Array.isArray(book)) {
    throw new Error("the book is not a mapping");
  }

  const shelf = new Map<string, string>();
  for (const key of Object.keys(book)) {
    if (!/^[a-z]+( [a-z]+)*$/.test(key)) {
      throw new Error("a key is not lowercase words parted by single spaces");
    }
    const value = book[key];
    if (typeof value !== "string" || !/^[a-z][a-z0-9]*$/.test(value)) {
      throw new Error("a value is not a contraction of lowercase letters and digits");
    }
    shelf.set(key, value);
  }

  const phrases = Object.keys(book).sort((left, right) => {
    if (left.length !== right.length) {
      return right.length - left.length;
    }
    return left < right ? -1 : left > right ? 1 : 0;
  });

  let out = "";
  let at = 0;
  while (at < text.length) {
    let hit: string | null = null;
    if (!wordish(at === 0 ? undefined : text.charAt(at - 1))) {
      for (const phrase of phrases) {
        const run = text.slice(at, at + phrase.length);
        if (run.length !== phrase.length || run.toLowerCase() !== phrase) {
          continue;
        }
        const after = at + phrase.length;
        if (after < text.length && wordish(text.charAt(after))) {
          continue;
        }
        hit = run;
        break;
      }
    }
    if (hit === null) {
      out += text.charAt(at);
      at += 1;
      continue;
    }
    const value = shelf.get(hit.toLowerCase()) as string;
    const opener = hit.charAt(0);
    out +=
      opener !== opener.toLowerCase()
        ? value.charAt(0).toUpperCase() + value.slice(1)
        : value;
    at += hit.length;
  }
  return out;
}
