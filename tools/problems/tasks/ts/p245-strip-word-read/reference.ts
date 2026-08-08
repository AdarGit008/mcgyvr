export function decodeBitRun(codebook: any, strip: string): string[] {
  if (typeof codebook !== "object" || codebook === null || Array.isArray(codebook)) {
    throw new Error("the codebook must be a mapping");
  }
  const words = Object.keys(codebook);
  if (words.length === 0) {
    throw new Error("the codebook names no words");
  }
  const marks: string[] = [];
  for (const word of words) {
    if (!/^[a-z]+$/.test(word)) {
      throw new Error("a key must be a non-empty string of lowercase letters");
    }
    const mark = codebook[word];
    if (typeof mark !== "string" || !/^[01]+$/.test(mark)) {
      throw new Error("a mark must be a non-empty string of 0 and 1");
    }
    marks.push(mark);
  }
  for (let i = 0; i < marks.length; i++) {
    for (let j = 0; j < marks.length; j++) {
      if (i === j) continue;
      if (marks[i] === marks[j]) {
        throw new Error("two words carry the same mark");
      }
      if (marks[j].startsWith(marks[i])) {
        throw new Error("one mark opens another mark");
      }
    }
  }
  if (typeof strip !== "string") {
    throw new Error("the strip must be a string");
  }
  if (strip.length > 0 && !/^[01]+$/.test(strip)) {
    throw new Error("the strip must hold nothing but 0 and 1");
  }
  const read: string[] = [];
  let at = 0;
  while (at < strip.length) {
    let found = -1;
    for (let width = 1; at + width <= strip.length; width++) {
      const ahead = strip.slice(at, at + width);
      const index = marks.indexOf(ahead);
      if (index !== -1) {
        found = index;
        at += width;
        break;
      }
    }
    if (found === -1) {
      throw new Error("the strip ends part-way through a mark");
    }
    read.push(words[found]);
  }
  return read;
}
