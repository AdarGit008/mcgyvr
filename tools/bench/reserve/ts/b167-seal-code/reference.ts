export function sealCode(code: string): string {
  if (typeof code !== "string" || code === "") {
    throw new Error("sealCode expects a non-empty string");
  }
  const glyphs = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  let seal = 7;
  for (const ch of code) {
    const worth = glyphs.indexOf(ch);
    if (worth < 0) {
      throw new Error("code holds a character outside digits and capitals");
    }
    seal = (seal * 2 + worth) % 36;
  }
  return code + glyphs[seal];
}
