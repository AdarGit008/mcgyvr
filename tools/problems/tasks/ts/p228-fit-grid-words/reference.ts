function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

export function fitGridWords(
  slots: Array<Record<string, unknown>>,
  words: string[],
): Record<string, unknown> {
  if (!Array.isArray(slots) || slots.length === 0) {
    throw new Error("the slots must be a non-empty list");
  }
  const ids: string[] = [];
  const spans: string[][] = [];
  const sizes: number[] = [];
  const seenId = new Set<string>();
  const held = new Map<string, string>();
  for (const slot of slots) {
    if (slot === null || typeof slot !== "object" || Array.isArray(slot)) {
      throw new Error("a slot must be a mapping");
    }
    const id = slot.id;
    const row = slot.row;
    const col = slot.col;
    const run = slot.run;
    const size = slot.len;
    if (typeof id !== "string" || id.length === 0) {
      throw new Error("an id must be a non-empty string");
    }
    if (seenId.has(id)) throw new Error("two slots share an id");
    seenId.add(id);
    if (!whole(row) || (row as number) < 0 || !whole(col) || (col as number) < 0) {
      throw new Error("a row and a column must be whole numbers of nought or more");
    }
    if (run !== "across" && run !== "down") {
      throw new Error("a run is either across or down");
    }
    if (!whole(size) || (size as number) < 2) {
      throw new Error("a length must be a whole number of two or more");
    }
    const span: string[] = [];
    for (let step = 0; step < (size as number); step++) {
      const at =
        run === "across"
          ? `${row as number},${(col as number) + step}`
          : `${(row as number) + step},${col as number}`;
      const key = `${run}|${at}`;
      if (held.has(key)) {
        throw new Error("two slots running the same way cover a square in common");
      }
      held.set(key, id);
      span.push(at);
    }
    ids.push(id);
    spans.push(span);
    sizes.push(size as number);
  }
  if (!Array.isArray(words)) throw new Error("the words must be a list");
  const seenWord = new Set<string>();
  for (const word of words) {
    if (typeof word !== "string" || !/^[a-z]+$/.test(word)) {
      throw new Error("a word must be lowercase letters a to z");
    }
    if (seenWord.has(word)) throw new Error("a word is offered twice");
    seenWord.add(word);
  }

  const grid = new Map<string, string>();
  const used = new Set<number>();
  const placed: Array<Record<string, string>> = [];
  let stuck = "";
  for (let at = 0; at < ids.length; at++) {
    let chosen = -1;
    for (let which = 0; which < words.length; which++) {
      if (used.has(which)) continue;
      const word = words[which];
      if (word.length !== sizes[at]) continue;
      let agrees = true;
      for (let step = 0; step < word.length; step++) {
        const letter = grid.get(spans[at][step]);
        if (letter !== undefined && letter !== word[step]) {
          agrees = false;
          break;
        }
      }
      if (agrees) {
        chosen = which;
        break;
      }
    }
    if (chosen < 0) {
      stuck = ids[at];
      break;
    }
    used.add(chosen);
    const word = words[chosen];
    for (let step = 0; step < word.length; step++) {
      grid.set(spans[at][step], word[step]);
    }
    placed.push({ slot: ids[at], word });
  }
  return { placed, stuck };
}
