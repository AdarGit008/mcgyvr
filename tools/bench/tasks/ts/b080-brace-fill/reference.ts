export function fillTemplate(template: string, values: Record<string, string>): string {
  if (typeof template !== "string") {
    throw new Error("fillTemplate expects a string template");
  }
  let out = "";
  let i = 0;
  while (i < template.length) {
    if (template[i] !== "{") {
      out += template[i];
      i += 1;
      continue;
    }
    const end = template.indexOf("}", i + 1);
    if (end === -1) {
      throw new Error("unterminated placeholder");
    }
    const name = template.slice(i + 1, end);
    if (!/^[A-Za-z0-9_]+$/.test(name)) {
      throw new Error("bad placeholder name: " + JSON.stringify(name));
    }
    if (!(name in values)) {
      throw new Error("unknown placeholder: " + name);
    }
    out += values[name];
    i = end + 1;
  }
  return out;
}
