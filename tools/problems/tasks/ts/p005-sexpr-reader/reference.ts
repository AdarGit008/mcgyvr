export function readSexpr(text: string): number | string | any[] {
  if (typeof text !== "string") {
    throw new Error("readSexpr expects a string");
  }
  let pos = 0;

  function skipWs(): void {
    while (pos < text.length && " \t\r\n".includes(text[pos])) {
      pos++;
    }
  }

  function parse(): number | string | any[] {
    skipWs();
    if (pos >= text.length) {
      throw new Error("unexpected end of input");
    }
    const ch = text[pos];
    if (ch === "(") {
      pos++;
      const items: any[] = [];
      for (;;) {
        skipWs();
        if (pos >= text.length) {
          throw new Error("unclosed list");
        }
        if (text[pos] === ")") {
          pos++;
          return items;
        }
        items.push(parse());
      }
    }
    if (ch === ")") {
      throw new Error("stray closing parenthesis");
    }
    const start = pos;
    while (pos < text.length && !" \t\r\n()".includes(text[pos])) {
      pos++;
    }
    const token = text.slice(start, pos);
    if (/^-?[0-9]+$/.test(token)) {
      return Number(token);
    }
    if (/^[0-9]/.test(token)) {
      throw new Error("atom starting with a digit must be an integer");
    }
    if (!/^[A-Za-z0-9+\-*/!?]+$/.test(token)) {
      throw new Error("atom has a character outside the symbol set");
    }
    return token;
  }

  const value = parse();
  skipWs();
  if (pos < text.length) {
    throw new Error("trailing content after the expression");
  }
  return value;
}
