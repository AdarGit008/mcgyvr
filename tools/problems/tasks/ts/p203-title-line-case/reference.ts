const TOKEN = /^[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*$/;

function dressToken(token: string): string {
  const pieces: string[] = [];
  const joints: string[] = [];
  let current = "";
  for (const ch of token) {
    if (ch === "'" || ch === "-") {
      pieces.push(current);
      joints.push(ch);
      current = "";
    } else {
      current += ch;
    }
  }
  pieces.push(current);
  const dressed = pieces.map((piece, at) => {
    if (at === pieces.length - 1 && pieces.length > 1 && piece.length === 1) {
      return piece.toLowerCase();
    }
    return piece[0].toUpperCase() + piece.slice(1).toLowerCase();
  });
  let out = dressed[0];
  for (let at = 0; at < joints.length; at += 1) {
    out += joints[at] + dressed[at + 1];
  }
  return out;
}

export function titleLine(text: string, quiet: string[]): string {
  if (typeof text !== "string" || text.length === 0) {
    throw new Error("the heading must be a non-empty string");
  }
  if (!Array.isArray(quiet)) {
    throw new Error("the quiet list must be a list");
  }
  for (const entry of quiet) {
    if (typeof entry !== "string" || !/^[a-z]+$/.test(entry)) {
      throw new Error("every quiet entry must be a string of small letters");
    }
  }
  const tokens = text.split(" ");
  for (const token of tokens) {
    if (!TOKEN.test(token)) {
      throw new Error("malformed token: " + JSON.stringify(token));
    }
  }
  const last = tokens.length - 1;
  return tokens
    .map((token, at) => {
      if (/^[A-Z]{2,}$/.test(token)) {
        return token;
      }
      if (at !== 0 && at !== last && quiet.includes(token.toLowerCase())) {
        return token.toLowerCase();
      }
      return dressToken(token);
    })
    .join(" ");
}
