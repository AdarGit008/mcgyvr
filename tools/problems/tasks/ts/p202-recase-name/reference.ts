const STYLES = ["snake", "kebab", "shout", "pascal", "camel"];

function isUpper(ch: string): boolean {
  return ch >= "A" && ch <= "Z";
}

function isLower(ch: string): boolean {
  return ch >= "a" && ch <= "z";
}

function isDigit(ch: string): boolean {
  return ch >= "0" && ch <= "9";
}

function cutWords(label: string): string[] {
  const words: string[] = [];
  for (const segment of label.split(/[_-]/)) {
    let at = 0;
    while (at < segment.length) {
      const head = segment[at];
      if (isDigit(head)) {
        let end = at;
        while (end < segment.length && isDigit(segment[end])) end += 1;
        words.push(segment.slice(at, end));
        at = end;
      } else if (isUpper(head)) {
        let end = at;
        while (end < segment.length && isUpper(segment[end])) end += 1;
        if (end - at === 1) {
          let tail = end;
          while (tail < segment.length && isLower(segment[tail])) tail += 1;
          words.push(segment.slice(at, tail));
          at = tail;
        } else {
          if (end < segment.length && isLower(segment[end])) end -= 1;
          words.push(segment.slice(at, end));
          at = end;
        }
      } else {
        let end = at;
        while (end < segment.length && isLower(segment[end])) end += 1;
        words.push(segment.slice(at, end));
        at = end;
      }
    }
  }
  return words;
}

function leadCapital(word: string): string {
  if (/^[0-9]+$/.test(word) || /^[A-Z]{2,}$/.test(word)) {
    return word;
  }
  return word[0].toUpperCase() + word.slice(1).toLowerCase();
}

export function recaseName(label: string, style: string): string {
  if (typeof label !== "string" || typeof style !== "string") {
    throw new Error("recaseName expects two strings");
  }
  if (!STYLES.includes(style)) {
    throw new Error("unknown style: " + style);
  }
  if (!/^[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)*$/.test(label)) {
    throw new Error("label is empty, oddly punctuated, or holds a stray character");
  }
  const words = cutWords(label);
  if (style === "snake") {
    return words.map((word) => word.toLowerCase()).join("_");
  }
  if (style === "kebab") {
    return words.map((word) => word.toLowerCase()).join("-");
  }
  if (style === "shout") {
    return words.map((word) => word.toUpperCase()).join("_");
  }
  if (style === "pascal") {
    return words.map(leadCapital).join("");
  }
  return words[0].toLowerCase() + words.slice(1).map(leadCapital).join("");
}
