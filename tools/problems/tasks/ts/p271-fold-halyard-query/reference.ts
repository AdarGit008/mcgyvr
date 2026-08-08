const HEXLOW = "0123456789abcdef";

function loosen(chunk: string): string {
  let out = "";
  let at = 0;
  while (at < chunk.length) {
    const glyph = chunk[at];
    if (glyph !== "_") {
      out += glyph;
      at += 1;
      continue;
    }
    const high = chunk[at + 1];
    const low = chunk[at + 2];
    if (high === undefined || low === undefined) {
      throw new Error("an underscore must be followed by two hex glyphs");
    }
    if (HEXLOW.indexOf(high) < 0 || HEXLOW.indexOf(low) < 0) {
      throw new Error("an underscore must be followed by two lower-case hex glyphs");
    }
    const code = HEXLOW.indexOf(high) * 16 + HEXLOW.indexOf(low);
    if (code < 0x21 || code > 0x7e) {
      throw new Error("an escape must name a visible glyph");
    }
    out += String.fromCharCode(code);
    at += 3;
  }
  return out;
}

function tighten(text: string): string {
  let out = "";
  for (const glyph of text) {
    if (glyph === "&") {
      out += "_26";
    } else if (glyph === ",") {
      out += "_2c";
    } else if (glyph === "=") {
      out += "_3d";
    } else if (glyph === "_") {
      out += "_5f";
    } else {
      out += glyph;
    }
  }
  return out;
}

export function foldHalyardQuery(text: string): string {
  if (typeof text !== "string") {
    throw new Error("the query must be text");
  }
  for (let at = 0; at < text.length; at++) {
    const code = text.charCodeAt(at);
    if (code < 0x21 || code > 0x7e) {
      throw new Error("the query carries a glyph outside the visible band");
    }
  }
  if (text === "") {
    return "";
  }
  const flags = new Set();
  const carried = new Map();
  for (const parameter of text.split("&")) {
    const marks = parameter.split("=").length - 1;
    if (marks > 1) {
      throw new Error("a parameter must not carry a second bare equals");
    }
    if (marks === 0) {
      const name = loosen(parameter).toLowerCase();
      if (name === "") {
        throw new Error("a parameter name must not be empty");
      }
      flags.add(name);
      continue;
    }
    const cut = parameter.indexOf("=");
    const name = loosen(parameter.slice(0, cut)).toLowerCase();
    if (name === "") {
      throw new Error("a parameter name must not be empty");
    }
    const value = loosen(parameter.slice(cut + 1));
    if (!carried.has(name)) {
      carried.set(name, new Set());
    }
    carried.get(name).add(value);
  }
  for (const name of flags) {
    if (carried.has(name)) {
      throw new Error("a name cannot stand alone and carry a value too");
    }
  }
  const out: string[] = [];
  for (const name of Array.from(flags).sort()) {
    out.push(tighten(name));
  }
  for (const name of Array.from(carried.keys()).sort()) {
    const values = Array.from(carried.get(name)).sort().map(tighten);
    out.push(tighten(name) + "=" + values.join(","));
  }
  return out.join("&");
}
