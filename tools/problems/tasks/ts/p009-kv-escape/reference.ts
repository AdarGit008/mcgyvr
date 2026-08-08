/** One line of key=value pairs, joined by &. */
function escapePart(text: string): string {
  return text.replaceAll("%", "%25").replaceAll("&", "%26").replaceAll("=", "%3D");
}

export function encodePairs(pairs: [string, string][]): string {
  if (!Array.isArray(pairs)) {
    throw new Error("encodePairs expects a list of pairs");
  }
  const parts: string[] = [];
  for (const pair of pairs) {
    if (!Array.isArray(pair) || pair.length !== 2) {
      throw new Error("each entry is a key-value pair");
    }
    const [key, value] = pair;
    if (typeof key !== "string" || typeof value !== "string") {
      throw new Error("keys and values must be strings");
    }
    if (key === "") {
      throw new Error("empty key");
    }
    parts.push(escapePart(key) + "=" + escapePart(value));
  }
  return parts.join("&");
}
