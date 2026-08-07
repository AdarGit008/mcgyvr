const STOPS = new Set([".", "!", "?"]);

export function splitProseSentences(
  passage: string,
  abbreviations: string[],
): string[] {
  if (typeof passage !== "string") {
    throw new Error("passage must be a string");
  }
  if (!Array.isArray(abbreviations)) {
    throw new Error("abbreviations must be a list");
  }
  for (const item of abbreviations) {
    if (typeof item !== "string") {
      throw new Error("every abbreviation must be a string");
    }
    if (!item.endsWith(".")) {
      throw new Error("every abbreviation must end in a period");
    }
    if (item.includes(" ")) {
      throw new Error("an abbreviation may not hold a space");
    }
  }
  const known = new Set(abbreviations);
  const sentences: string[] = [];
  let quoted = false;
  let depth = 0;
  let start = 0;
  let at = 0;
  while (at < passage.length) {
    const ch = passage[at];
    if (ch === '"') {
      quoted = !quoted;
      at += 1;
      continue;
    }
    if (!quoted && ch === "(") {
      depth += 1;
      at += 1;
      continue;
    }
    if (!quoted && ch === ")") {
      depth -= 1;
      if (depth < 0) {
        throw new Error("closing bracket with no opener");
      }
      at += 1;
      continue;
    }
    if (!quoted && depth === 0 && STOPS.has(ch)) {
      let last = at;
      while (last + 1 < passage.length && STOPS.has(passage[last + 1])) {
        last += 1;
      }
      const after = last + 1;
      if (after < passage.length && passage[after] !== " ") {
        at = after;
        continue;
      }
      let head = last;
      while (head > 0 && passage[head - 1] !== " ") {
        head -= 1;
      }
      if (known.has(passage.slice(head, last + 1))) {
        at = after;
        continue;
      }
      const piece = passage.slice(start, after).trim();
      if (piece !== "") {
        sentences.push(piece);
      }
      at = after;
      start = after;
      continue;
    }
    at += 1;
  }
  if (depth !== 0) {
    throw new Error("bracket left open");
  }
  if (quoted) {
    throw new Error("quotation left open");
  }
  const tail = passage.slice(start).trim();
  if (tail !== "") {
    sentences.push(tail);
  }
  return sentences;
}
