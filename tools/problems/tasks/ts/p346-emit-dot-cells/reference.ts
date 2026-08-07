const BASE = ["1", "12", "14", "145", "15", "124", "1245", "125", "24", "245"];
const CAPITAL = "6";
const NUMBER = "3456";
const BLANK = "0";

function raise(pattern: string, extra: string): string {
  const dots = new Set((pattern + extra).split(""));
  return [...dots].sort().join("");
}

function buildCells(): Record<string, string> {
  const cells: Record<string, string> = {};
  const first = "abcdefghij";
  for (let i = 0; i < 10; i += 1) {
    cells[first[i]] = BASE[i];
    cells["klmnopqrst"[i]] = raise(BASE[i], "3");
  }
  const late = "uvxyz";
  for (let i = 0; i < late.length; i += 1) {
    cells[late[i]] = raise(BASE[i], "36");
  }
  cells["w"] = "2456";
  return cells;
}

const CELLS = buildCells();

export function emitDotCells(text: string): string {
  if (typeof text !== "string") {
    throw new Error("the argument must be a string");
  }
  if (text.length === 0) {
    throw new Error("the argument must not be empty");
  }
  const out: string[] = [];
  let inRun = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === " ") {
      if (i > 0 && text[i - 1] === " ") {
        throw new Error("two spaces may not stand next to each other");
      }
      out.push(BLANK);
      inRun = false;
      continue;
    }
    if (ch >= "0" && ch <= "9") {
      if (!inRun) {
        out.push(NUMBER);
        inRun = true;
      }
      const digit = ch === "0" ? 9 : ch.charCodeAt(0) - 49;
      out.push(BASE[digit]);
      continue;
    }
    inRun = false;
    if (ch >= "A" && ch <= "Z") {
      out.push(CAPITAL);
      out.push(CELLS[ch.toLowerCase()]);
      continue;
    }
    if (ch >= "a" && ch <= "z") {
      out.push(CELLS[ch]);
      continue;
    }
    throw new Error("only ASCII letters, ASCII digits and spaces may be rendered");
  }
  return out.join("-");
}
