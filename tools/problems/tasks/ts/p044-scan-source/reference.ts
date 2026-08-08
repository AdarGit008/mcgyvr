export function scanSource(line: string): [string, string][] {
  if (typeof line !== "string") {
    throw new Error("input must be a string");
  }
  const twoChar = ["==", "!=", "<=", ">=", "&&", "||"];
  const oneChar = "=<>+-*/()";
  const tokens: [string, string][] = [];
  let i = 0;
  while (i < line.length) {
    const ch = line[i];
    if (ch === " " || ch === "\t") {
      i++;
      continue;
    }
    if (/\d/.test(ch)) {
      let j = i;
      while (j < line.length && /\d/.test(line[j])) j++;
      tokens.push(["num", line.slice(i, j)]);
      i = j;
      continue;
    }
    if (/[A-Za-z_]/.test(ch)) {
      let j = i;
      while (j < line.length && /[A-Za-z0-9_]/.test(line[j])) j++;
      tokens.push(["id", line.slice(i, j)]);
      i = j;
      continue;
    }
    const pair = line.slice(i, i + 2);
    if (twoChar.includes(pair)) {
      tokens.push(["op", pair]);
      i += 2;
      continue;
    }
    if (oneChar.includes(ch)) {
      tokens.push(["op", ch]);
      i++;
      continue;
    }
    throw new Error("unexpected character");
  }
  return tokens;
}
