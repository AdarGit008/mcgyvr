export function computeSheet(
  cells: Record<string, string>,
): Record<string, number> {
  if (cells === null || typeof cells !== "object" || Array.isArray(cells)) {
    throw new Error("computeSheet expects an object of cells");
  }
  const values: Record<string, number> = {};
  const visiting = new Set<string>();

  const evaluate = (name: string): number => {
    if (name in values) {
      return values[name];
    }
    if (!(name in cells)) {
      throw new Error(`unknown cell ${name}`);
    }
    if (visiting.has(name)) {
      throw new Error(`reference cycle through ${name}`);
    }
    visiting.add(name);
    const raw = cells[name];
    let result: number;
    if (typeof raw !== "string") {
      throw new Error("cell text must be a string");
    }
    if (raw.startsWith("=")) {
      const body = raw.slice(1);
      if (body.trim() === "") {
        throw new Error("empty formula");
      }
      result = 0;
      for (const part of body.split("+")) {
        const term = part.trim();
        if (/^-?\d+$/.test(term)) {
          result += Number(term);
        } else if (/^[A-Z]+\d+$/.test(term)) {
          result += evaluate(term);
        } else {
          throw new Error(`malformed term ${term}`);
        }
      }
    } else if (/^-?\d+$/.test(raw.trim())) {
      result = Number(raw.trim());
    } else {
      throw new Error(`malformed literal ${raw}`);
    }
    visiting.delete(name);
    values[name] = result;
    return result;
  };

  for (const name of Object.keys(cells)) {
    evaluate(name);
  }
  return values;
}
