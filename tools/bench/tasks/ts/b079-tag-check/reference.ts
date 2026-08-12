export function lineTag(body: string): string {
  if (typeof body !== "string") {
    throw new Error("lineTag expects a string");
  }
  let sum = 0;
  for (const ch of body) {
    sum = (sum + ch.codePointAt(0)!) % 256;
  }
  return sum.toString(16).padStart(2, "0");
}

export function checkLine(line: string): string {
  if (typeof line !== "string") {
    throw new Error("checkLine expects a string");
  }
  if (line.length < 3 || line[line.length - 3] !== "~") {
    throw new Error("missing tag separator");
  }
  const body = line.slice(0, -3);
  if (line.slice(-2) !== lineTag(body)) {
    throw new Error("tag does not match body");
  }
  return body;
}
