const STEM = /^[A-Za-z][A-Za-z0-9-]*$/;
const NAME = /^[a-z][a-z0-9-]*$/;

export function readTagAttributes(tag: string): Record<string, unknown> {
  if (typeof tag !== "string") {
    throw new Error("the tag must be a string");
  }
  const size = tag.length;
  if (size === 0 || tag[0] !== "[") {
    throw new Error("the tag must open with a left square bracket");
  }
  let at = 1;

  let cut = at;
  while (at < size && /[A-Za-z0-9-]/.test(tag[at])) at += 1;
  const stem = tag.slice(cut, at);
  if (!STEM.test(stem)) {
    throw new Error("the stem breaks its shape: " + stem);
  }

  const marks: Array<Record<string, string>> = [];
  const settled = new Map<string, string>();

  for (;;) {
    if (at >= size) {
      throw new Error("the tag never closes");
    }
    if (tag[at] === "]") {
      at += 1;
      break;
    }
    if (tag[at] !== " ") {
      throw new Error("a stray character sits where a space belongs: " + tag[at]);
    }
    at += 1;
    if (at >= size) {
      throw new Error("the tag never closes");
    }
    if (tag[at] === " ") {
      throw new Error("two spaces running");
    }
    if (tag[at] === "]") {
      throw new Error("a space stands before the closing bracket");
    }

    cut = at;
    while (at < size && /[a-z0-9-]/.test(tag[at])) at += 1;
    const name = tag.slice(cut, at);
    if (!NAME.test(name)) {
      throw new Error("a mark name breaks its shape: " + name);
    }

    let setting = "";
    if (at < size && tag[at] === "=") {
      at += 1;
      if (at >= size) {
        throw new Error("an equals sign with no setting after it");
      }
      const fence = tag[at];
      if (fence === '"' || fence === "'") {
        at += 1;
        let out = "";
        for (;;) {
          if (at >= size) {
            throw new Error("a fence is never closed");
          }
          const ch = tag[at];
          if (ch === "\\") {
            const next = tag[at + 1];
            if (next !== fence && next !== "\\") {
              throw new Error("a backslash stands before something it may not");
            }
            out += next;
            at += 2;
            continue;
          }
          if (ch === fence) {
            at += 1;
            break;
          }
          out += ch;
          at += 1;
        }
        setting = out;
      } else {
        cut = at;
        while (at < size && /[A-Za-z0-9._-]/.test(tag[at])) at += 1;
        setting = tag.slice(cut, at);
        if (setting.length === 0) {
          throw new Error("an equals sign with no setting after it");
        }
      }
    }

    if (settled.has(name)) {
      if (settled.get(name) !== setting) {
        throw new Error("the name " + name + " is carried twice with different settings");
      }
    } else {
      settled.set(name, setting);
      marks.push({ name, setting });
    }
  }

  if (at !== size) {
    throw new Error("something follows the closing bracket");
  }
  return { stem, marks };
}
