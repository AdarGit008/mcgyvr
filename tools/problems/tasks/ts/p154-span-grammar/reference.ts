type Part =
  | { kind: "lit"; text: string }
  | { kind: "choices"; options: string[] };

export function expandSpanGrammar(pattern: string): string[] {
  if (typeof pattern !== "string") {
    throw new Error("pattern must be a string");
  }
  const parts: Part[] = [];
  let literal = "";
  let i = 0;
  while (i < pattern.length) {
    const ch = pattern[i];
    if (ch === "~") {
      const next = pattern[i + 1];
      if (next === undefined || !"<>|~".includes(next)) {
        throw new Error("bad escape");
      }
      literal += next;
      i += 2;
    } else if (ch === ">") {
      throw new Error("stray group close");
    } else if (ch === "<") {
      const end = pattern.indexOf(">", i + 1);
      if (end === -1) {
        throw new Error("unclosed group");
      }
      const body = pattern.slice(i + 1, end);
      if (body.includes("<") || body.includes("~")) {
        throw new Error("forbidden character in group");
      }
      if (literal !== "") {
        parts.push({ kind: "lit", text: literal });
        literal = "";
      }
      parts.push({ kind: "choices", options: groupOptions(body) });
      i = end + 1;
    } else {
      literal += ch;
      i += 1;
    }
  }
  if (literal !== "") {
    parts.push({ kind: "lit", text: literal });
  }
  let count = 1;
  for (const part of parts) {
    if (part.kind === "choices") {
      count *= part.options.length;
    }
    if (count > 500) {
      throw new Error("too many combinations");
    }
  }
  let results = [""];
  for (const part of parts) {
    const options = part.kind === "lit" ? [part.text] : part.options;
    const next: string[] = [];
    for (const stem of results) {
      for (const option of options) {
        next.push(stem + option);
      }
    }
    results = next;
  }
  return [...new Set(results)].sort();
}

function groupOptions(body: string): string[] {
  if (body.includes("..")) {
    const m = /^(\d+)\.\.(\d+)$/.exec(body);
    if (m === null) {
      throw new Error("malformed span");
    }
    const lo = Number(m[1]);
    const hi = Number(m[2]);
    if (lo > hi) {
      throw new Error("span out of order");
    }
    if (hi - lo + 1 > 500) {
      throw new Error("too many combinations");
    }
    const width = m[1].length;
    const options: string[] = [];
    for (let v = lo; v <= hi; v++) {
      options.push(String(v).padStart(width, "0"));
    }
    return options;
  }
  const options = body.split("|");
  for (const option of options) {
    if (!/^[A-Za-z0-9]+$/.test(option)) {
      throw new Error("bad alternation choice");
    }
  }
  return options;
}
