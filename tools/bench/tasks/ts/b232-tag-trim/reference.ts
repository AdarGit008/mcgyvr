export function tagTrim(tag: string): string {
  let out = tag;
  if (out.startsWith("#")) {
    out = out.slice(1);
  }
  if (out.endsWith(":")) {
    out = out.slice(0, -1);
  }
  return out;
}
