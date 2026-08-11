export function badgeText(pattern: string, fields: Record<string, string>): string {
  if (typeof pattern !== "string") {
    throw new Error("badgeText expects a string pattern");
  }
  let out = "";
  let i = 0;
  while (i < pattern.length) {
    if (pattern[i] === ">") throw new Error("a closing bracket sits outside any slot");
    if (pattern[i] !== "<") { out += pattern[i]; i += 1; continue; }
    const end = pattern.indexOf(">", i + 1);
    if (end < 0) throw new Error("an opening bracket is never closed");
    const name = pattern.slice(i + 1, end);
    if (!/^[a-z]+$/.test(name)) throw new Error("slot name must be lowercase letters");
    if (!Object.hasOwn(fields, name)) throw new Error("the fields mapping holds no such name");
    out += fields[name];
    i = end + 1;
  }
  return out;
}
