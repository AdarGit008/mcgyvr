/** A tag tree drawn down to a measured width. */
const HEAD = /^[a-z]+$/;
const WORD = /^[a-z0-9]+$/;

function isTag(thing: any): boolean {
  return thing !== null && typeof thing === "object" && !Array.isArray(thing);
}

function check(thing: any): void {
  if (typeof thing === "string") {
    if (!WORD.test(thing)) {
      throw new Error("a word is small letters and digits only");
    }
    return;
  }
  if (!isTag(thing)) {
    throw new Error("an item is either a word or a tag");
  }
  if (!("head" in thing) || !("items" in thing)) {
    throw new Error("a tag needs both head and items");
  }
  if (typeof thing.head !== "string" || !HEAD.test(thing.head)) {
    throw new Error("a head is small letters only");
  }
  if (!Array.isArray(thing.items)) {
    throw new Error("items must be a list");
  }
  for (const item of thing.items) {
    check(item);
  }
}

function tight(thing: any): string {
  if (typeof thing === "string") {
    return thing;
  }
  return thing.head + "(" + thing.items.map(tight).join(", ") + ")";
}

export function fitTagLines(node: any, width: number): string {
  if (typeof width !== "number" || !Number.isInteger(width) || width < 1) {
    throw new Error("the width must be a whole number of one or more");
  }
  if (typeof node === "string") {
    throw new Error("an item is either a word or a tag");
  }
  check(node);

  const draw = (thing: any, depth: number): string[] => {
    const pad = "  ".repeat(depth);
    const one = tight(thing);
    if (typeof thing === "string" || pad.length + one.length <= width) {
      return [pad + one];
    }
    const lines = [pad + thing.head + "("];
    thing.items.forEach((item: any, index: number) => {
      const kid = draw(item, depth + 1);
      if (index < thing.items.length - 1) {
        kid[kid.length - 1] += ",";
      }
      lines.push(...kid);
    });
    lines.push(pad + ")");
    return lines;
  };
  return draw(node, 0).join("\n");
}
