const NAME = /^[a-z]+$/;

function isCrate(value: any): boolean {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isFlat(value: any): boolean {
  return typeof value === "number" || typeof value === "string";
}

function pad(level: number): string {
  return "..".repeat(level);
}

function drawFlat(value: any): string {
  if (typeof value === "number") {
    if (!Number.isInteger(value)) {
      throw new Error("a number must be whole");
    }
    return String(value);
  }
  if (/[<>\n]/.test(value)) {
    throw new Error("a string may hold no line break and no angle bracket");
  }
  return "<" + value + ">";
}

function order(names: string[]): string[] {
  return [...names].sort((a, b) =>
    a.length !== b.length ? a.length - b.length : a < b ? -1 : a > b ? 1 : 0,
  );
}

function draw(value: any, level: number): string[] {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return [pad(level) + "[]"];
    }
    const lines = [pad(level) + "["];
    for (const item of value) {
      if (isFlat(item)) {
        lines.push(pad(level + 1) + drawFlat(item));
      } else if (Array.isArray(item) || isCrate(item)) {
        lines.push(...draw(item, level + 1));
      } else {
        throw new Error("a value must be a number, a string, a list or a crate");
      }
    }
    lines.push(pad(level) + "]");
    return lines;
  }
  if (!isCrate(value)) {
    throw new Error("a value must be a number, a string, a list or a crate");
  }
  const names = Object.keys(value);
  for (const name of names) {
    if (!NAME.test(name)) {
      throw new Error("a field name is small letters only");
    }
  }
  if (names.length === 0) {
    return [pad(level) + "{}"];
  }
  const flat = order(names.filter((name) => isFlat(value[name])));
  const deep = order(names.filter((name) => !isFlat(value[name])));
  const lines = [pad(level) + "{"];
  for (const name of [...flat, ...deep]) {
    const held = value[name];
    if (isFlat(held)) {
      lines.push(pad(level + 1) + name + " -> " + drawFlat(held));
    } else if (Array.isArray(held) || isCrate(held)) {
      lines.push(pad(level + 1) + name + " ->");
      lines.push(...draw(held, level + 2));
    } else {
      throw new Error("a value must be a number, a string, a list or a crate");
    }
  }
  lines.push(pad(level) + "}");
  return lines;
}

export function renderCrateBlock(crate: any): string {
  if (!isCrate(crate)) {
    throw new Error("the argument must be a crate");
  }
  return draw(crate, 0).join("\n");
}
