function whole(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isLower(ch: string): boolean {
  return ch >= "a" && ch <= "z";
}

function isDigit(ch: string): boolean {
  return ch >= "0" && ch <= "9";
}

export function expandMacroCalls(
  macros: Record<string, unknown>[],
  source: string,
  bound: number,
): string {
  if (!whole(bound) || bound < 1) {
    throw new Error("the bound is not whole or falls below one");
  }
  if (typeof source !== "string") {
    throw new Error("the source is not a string");
  }
  if (!Array.isArray(macros)) {
    throw new Error("expandMacroCalls expects a list of macros");
  }

  const table = new Map<string, { arity: number; body: string }>();
  for (const macro of macros) {
    if (!isRecord(macro)) {
      throw new Error("a macro is not a record");
    }
    if (Object.keys(macro).sort().join(",") !== "arity,body,name") {
      throw new Error("a macro's keys are not exactly the three named");
    }
    const name = macro["name"];
    if (typeof name !== "string" || !/^[a-z][a-z0-9]*$/.test(name)) {
      throw new Error("a macro name is malformed");
    }
    if (table.has(name)) {
      throw new Error("two macros answer to one name");
    }
    const arity = macro["arity"];
    if (!whole(arity) || Number(arity) < 0 || Number(arity) > 9) {
      throw new Error("an arity is not whole or falls outside nought through nine");
    }
    if (typeof macro["body"] !== "string") {
      throw new Error("a body is not a string");
    }
    table.set(name, { arity: Number(arity), body: String(macro["body"]) });
  }

  const fill = (body: string, args: string[], arity: number): string => {
    let out = "";
    let at = 0;
    while (at < body.length) {
      const ch = body[at];
      if (ch !== "#") {
        out += ch;
        at++;
        continue;
      }
      const next = body[at + 1];
      if (next === "#") {
        out += "#";
        at += 2;
        continue;
      }
      if (next !== undefined && isDigit(next)) {
        const place = Number(next);
        if (place < 1 || place > arity) {
          throw new Error("a body names a place the macro's arity does not reach");
        }
        out += args[place - 1];
        at += 2;
        continue;
      }
      throw new Error("a stray hash stands in a body");
    }
    return out;
  };

  const walk = (text: string, depth: number): string => {
    let out = "";
    let at = 0;
    while (at < text.length) {
      const ch = text[at];
      if (ch !== "@") {
        out += ch;
        at++;
        continue;
      }
      if (text[at + 1] === "@") {
        out += "@";
        at += 2;
        continue;
      }
      const head = text[at + 1];
      if (head === undefined || !isLower(head)) {
        throw new Error("a stray at sign stands in the text");
      }
      let end = at + 1;
      while (end < text.length && (isLower(text[end]) || isDigit(text[end]))) {
        end++;
      }
      const name = text.slice(at + 1, end);

      let args: string[] = [];
      if (text[end] === "{") {
        const pieces: string[] = [];
        let piece = "";
        let nest = 1;
        let cursor = end + 1;
        while (cursor < text.length && nest > 0) {
          const inner = text[cursor];
          if (inner === "{") {
            nest++;
            piece += inner;
          } else if (inner === "}") {
            nest--;
            if (nest > 0) {
              piece += inner;
            }
          } else if (inner === "|" && nest === 1) {
            pieces.push(piece);
            piece = "";
          } else {
            piece += inner;
          }
          cursor++;
        }
        if (nest !== 0) {
          throw new Error("a brace is never closed");
        }
        pieces.push(piece);
        args = pieces;
        at = cursor;
      } else {
        at = end;
      }

      const macro = table.get(name);
      if (macro === undefined) {
        throw new Error("the text calls a macro that was never declared");
      }
      if (args.length !== macro.arity) {
        throw new Error("a call's argument count differs from the arity");
      }
      if (depth + 1 > bound) {
        throw new Error("the expansion runs deeper than the bound");
      }
      out += walk(fill(macro.body, args, macro.arity), depth + 1);
    }
    return out;
  };

  return walk(source, 0);
}
