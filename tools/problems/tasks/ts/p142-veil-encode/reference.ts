export function veilEncode(keyword: string, message: string): string {
  if (typeof keyword !== "string" || keyword.length === 0) {
    throw new Error("keyword must be a non-empty string");
  }
  if (!/^[a-z]+$/.test(keyword)) {
    throw new Error("keyword must be lowercase a-z only");
  }
  if (typeof message !== "string") {
    throw new Error("message must be a string");
  }
  if (!/^[a-z ]*$/.test(message)) {
    throw new Error("message must be lowercase a-z and spaces only");
  }
  const veil: string[] = [];
  for (const ch of keyword) {
    if (!veil.includes(ch)) {
      veil.push(ch);
    }
  }
  const alphabet = "abcdefghijklmnopqrstuvwxyz";
  for (const ch of [...alphabet].reverse()) {
    if (!veil.includes(ch)) {
      veil.push(ch);
    }
  }
  let encoded = "";
  for (const ch of message) {
    encoded += ch === " " ? " " : veil[ch.charCodeAt(0) - 97];
  }
  return encoded;
}
