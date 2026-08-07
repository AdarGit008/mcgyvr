const MARKS = new Set([".", "!", "?"]);

function isDigit(ch: string): boolean {
  return ch >= "0" && ch <= "9";
}

function isLetter(ch: string): boolean {
  return (ch >= "a" && ch <= "z") || (ch >= "A" && ch <= "Z");
}

export function countSentences(prose: string, titles: string[]): number {
  if (typeof prose !== "string") {
    throw new Error("prose must be a string");
  }
  if (!Array.isArray(titles)) {
    throw new Error("titles must be a list");
  }
  for (const title of titles) {
    if (typeof title !== "string" || title.length === 0) {
      throw new Error("a title must be a non-empty string");
    }
    for (const ch of title) {
      if (!isLetter(ch)) {
        throw new Error("a title must be a run of letters");
      }
    }
  }
  const known = new Set(titles);
  let endings = 0;
  let depth = 0;
  let aside = false;
  let at = 0;
  let tailFrom = 0;
  while (at < prose.length) {
    const ch = prose[at];
    if (ch === "'") {
      aside = !aside;
      at += 1;
      continue;
    }
    if (ch === "[") {
      depth += 1;
      at += 1;
      continue;
    }
    if (ch === "]") {
      depth -= 1;
      if (depth < 0) {
        throw new Error("a square bracket was closed with no opener");
      }
      at += 1;
      continue;
    }
    if (!aside && depth === 0 && MARKS.has(ch)) {
      let last = at;
      while (last + 1 < prose.length && MARKS.has(prose[last + 1])) {
        last += 1;
      }
      const after = last + 1;
      let inert = false;
      if (ch === "." && last === at) {
        const prev = at - 1;
        if (
          prev >= 0 &&
          isDigit(prose[prev]) &&
          after < prose.length &&
          isDigit(prose[after])
        ) {
          inert = true;
        }
        let head = at;
        while (head > 0 && isLetter(prose[head - 1])) {
          head -= 1;
        }
        if (head < at && known.has(prose.slice(head, at))) {
          inert = true;
        }
        if (
          prev >= 0 &&
          prose[prev] >= "A" &&
          prose[prev] <= "Z" &&
          (prev === 0 || prose[prev - 1] === " ")
        ) {
          inert = true;
        }
      }
      if (!inert) {
        endings += 1;
        tailFrom = after;
      }
      at = after;
      continue;
    }
    at += 1;
  }
  if (depth !== 0) {
    throw new Error("a square bracket was left open");
  }
  if (aside) {
    throw new Error("an aside was left open");
  }
  if (prose.slice(tailFrom).trim() !== "") {
    endings += 1;
  }
  return endings;
}
