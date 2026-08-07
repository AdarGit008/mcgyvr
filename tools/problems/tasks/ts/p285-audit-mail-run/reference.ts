type Entry = { bin: string; grades: string; offices: string[] };
type Item = { code: string; stamped: string };
type Slip = { code: string; stamped: string; correct: string };
type Count = { bin: string; count: number };

const CODE = /^[PLE][A-Z]{2}[0-9]{3}$/;
const OFFICE = /^[A-Z]{2}$/;

function place(letter: string): number {
  return letter.charCodeAt(0) - 64;
}

export function auditMailRun(
  items: Item[],
  plan: Entry[],
): { misrouted: Slip[]; tally: Count[] } {
  if (!Array.isArray(plan) || plan.length === 0) {
    throw new Error("plan must be a non-empty list");
  }
  const bins = new Set<string>();
  for (const entry of plan) {
    if (entry === null || typeof entry !== "object") {
      throw new Error("a plan entry must be a record");
    }
    if (typeof entry.bin !== "string" || entry.bin.length === 0) {
      throw new Error("a bin must be a non-empty string");
    }
    if (entry.bin === "QUERY" || entry.bin === "SPARE") {
      throw new Error("a plan bin may not be " + entry.bin);
    }
    if (bins.has(entry.bin)) {
      throw new Error("bins repeat: " + entry.bin);
    }
    bins.add(entry.bin);
    const grades = entry.grades;
    if (
      typeof grades !== "string" ||
      grades.length === 0 ||
      grades.length > 3 ||
      new Set(grades).size !== grades.length
    ) {
      throw new Error("grades must be one to three distinct letters");
    }
    for (const grade of grades) {
      if (!"PLE".includes(grade)) {
        throw new Error("unknown grade letter: " + grade);
      }
    }
    if (!Array.isArray(entry.offices) || entry.offices.length === 0) {
      throw new Error("offices must be a non-empty list");
    }
    const here = new Set<string>();
    for (const office of entry.offices) {
      if (typeof office !== "string" || !OFFICE.test(office)) {
        throw new Error("an office must be two capital letters");
      }
      if (here.has(office)) {
        throw new Error("offices repeat: " + office);
      }
      here.add(office);
    }
  }
  if (!Array.isArray(items)) {
    throw new Error("items must be a list");
  }
  for (const item of items) {
    if (item === null || typeof item !== "object") {
      throw new Error("an item must be a record");
    }
    if (typeof item.code !== "string" || !CODE.test(item.code)) {
      throw new Error("an item code must be six characters of the grammar");
    }
    if (typeof item.stamped !== "string" || item.stamped.length === 0) {
      throw new Error("a stamped bin must be a non-empty string");
    }
  }

  const misrouted: Slip[] = [];
  const counts = new Map<string, number>();
  for (const item of items) {
    const code = item.code;
    const sum =
      Number(code[3]) + Number(code[4]) + place(code[1]) + place(code[2]);
    let correct = "";
    if (sum % 10 !== Number(code[5])) {
      correct = "QUERY";
    } else {
      correct = "SPARE";
      for (const entry of plan) {
        if (entry.grades.includes(code[0]) && entry.offices.includes(code.slice(1, 3))) {
          correct = entry.bin;
          break;
        }
      }
    }
    counts.set(correct, (counts.get(correct) ?? 0) + 1);
    if (item.stamped !== correct) {
      misrouted.push({ code, stamped: item.stamped, correct });
    }
  }

  const names = [...counts.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const tally: Count[] = names.map((bin) => ({
    bin,
    count: counts.get(bin) as number,
  }));
  return { misrouted, tally };
}
