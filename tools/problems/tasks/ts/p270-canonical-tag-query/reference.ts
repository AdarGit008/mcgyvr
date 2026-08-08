const HEX = "0123456789ABCDEF";

function unwrap(chunk: string): string {
  let out = "";
  let at = 0;
  while (at < chunk.length) {
    const glyph = chunk[at];
    if (glyph !== "~") {
      out += glyph;
      at += 1;
      continue;
    }
    const high = chunk[at + 1];
    const low = chunk[at + 2];
    if (high === undefined || low === undefined) {
      throw new Error("a tilde must be followed by two hex glyphs");
    }
    if (HEX.indexOf(high) < 0 || HEX.indexOf(low) < 0) {
      throw new Error("a tilde must be followed by two upper-case hex glyphs");
    }
    const code = HEX.indexOf(high) * 16 + HEX.indexOf(low);
    if (code < 0x20 || code > 0x7e) {
      throw new Error("an escape must name a printable glyph");
    }
    out += String.fromCharCode(code);
    at += 3;
  }
  return out;
}

function wrap(text: string): string {
  let out = "";
  for (const glyph of text) {
    if (glyph === ":") {
      out += "~3A";
    } else if (glyph === ";") {
      out += "~3B";
    } else if (glyph === "~") {
      out += "~7E";
    } else {
      out += glyph;
    }
  }
  return out;
}

export function canonicalTagQuery(text: string): string {
  if (typeof text !== "string") {
    throw new Error("the query must be text");
  }
  for (let at = 0; at < text.length; at++) {
    const code = text.charCodeAt(at);
    if (code < 0x20 || code > 0x7e) {
      throw new Error("the query carries a glyph outside the printable band");
    }
  }
  if (text === "") {
    return "";
  }
  const pairs: string[][] = [];
  for (const item of text.split(";")) {
    const colons = item.split(":").length - 1;
    if (colons === 0) {
      throw new Error("every item must carry a colon");
    }
    if (colons > 1) {
      throw new Error("an item must not carry a second bare colon");
    }
    const cut = item.indexOf(":");
    const key = unwrap(item.slice(0, cut));
    const value = unwrap(item.slice(cut + 1));
    if (key === "") {
      throw new Error("an item key must not be empty");
    }
    pairs.push([key, value]);
  }
  pairs.sort((a, b) => {
    if (a[0] !== b[0]) {
      return a[0] < b[0] ? -1 : 1;
    }
    if (a[1] === b[1]) {
      return 0;
    }
    return a[1] < b[1] ? -1 : 1;
  });
  const kept: string[] = [];
  for (let at = 0; at < pairs.length; at++) {
    if (
      at > 0 &&
      pairs[at][0] === pairs[at - 1][0] &&
      pairs[at][1] === pairs[at - 1][1]
    ) {
      continue;
    }
    kept.push(wrap(pairs[at][0]) + ":" + wrap(pairs[at][1]));
  }
  return kept.join(";");
}
