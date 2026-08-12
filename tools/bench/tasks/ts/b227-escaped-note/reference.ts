export function decodeEscapedNote(text: string): string {
  const lines = text.split("\n").map((line) => line.replace(/[ \t]+$/, ""));
  let folded = lines[0];
  for (let n = 1; n < lines.length; n++) {
    if (folded.endsWith("=")) {
      folded = folded.slice(0, -1) + lines[n];
    } else {
      folded = folded + "\n" + lines[n];
    }
  }
  let out = "";
  let i = 0;
  while (i < folded.length) {
    if (folded[i] === "=") {
      const pair = folded.slice(i + 1, i + 3);
      if (!/^[0-9A-F]{2}$/.test(pair)) {
        throw new Error("bad escape in note");
      }
      out += String.fromCharCode(parseInt(pair, 16));
      i += 3;
    } else {
      out += folded[i];
      i += 1;
    }
  }
  return out;
}
