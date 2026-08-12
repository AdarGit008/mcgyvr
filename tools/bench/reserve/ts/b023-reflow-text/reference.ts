/** Greedy re-wrap of free text into lines of a fixed width. */

function paragraphsOf(text: string): string[][] {
  const paragraphs: string[][] = [];
  let words: string[] = [];
  for (const line of text.split("\n")) {
    const tokens = line.split(/[ \t]+/).filter((token) => token.length > 0);
    if (tokens.length === 0) {
      if (words.length > 0) {
        paragraphs.push(words);
        words = [];
      }
    } else {
      words.push(...tokens);
    }
  }
  if (words.length > 0) {
    paragraphs.push(words);
  }
  return paragraphs;
}

export function reflowText(text: string, width: number): string[] {
  if (typeof text !== "string") {
    throw new Error("text must be a string");
  }
  if (!Number.isInteger(width) || width < 1) {
    throw new Error("width must be a positive integer");
  }
  const lines: string[] = [];
  const paragraphs = paragraphsOf(text);
  for (let p = 0; p < paragraphs.length; p++) {
    if (p > 0) {
      lines.push("");
    }
    let current = "";
    for (const word of paragraphs[p]) {
      if (word.length > width) {
        if (current.length > 0) {
          lines.push(current);
        }
        let rest = word;
        while (rest.length > width) {
          lines.push(rest.slice(0, width));
          rest = rest.slice(width);
        }
        current = rest;
      } else if (current.length === 0) {
        current = word;
      } else if (current.length + 1 + word.length <= width) {
        current = `${current} ${word}`;
      } else {
        lines.push(current);
        current = word;
      }
    }
    if (current.length > 0) {
      lines.push(current);
    }
  }
  return lines;
}
