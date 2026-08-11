export function expandMarkers(
  template: string,
  values: Record<string, string>,
): string {
  if (typeof template !== "string") {
    throw new Error("expandMarkers expects a string template");
  }
  const shape = /^[A-Za-z_][A-Za-z0-9_]*$/;
  let out = "";
  let i = 0;
  while (i < template.length) {
    const ch = template[i];
    if (ch !== "%") {
      out += ch;
      i += 1;
      continue;
    }
    if (template[i + 1] === "%") {
      out += "%";
      i += 2;
      continue;
    }
    const close = template.indexOf("%", i + 1);
    if (close === -1) {
      throw new Error("marker opened and never closed");
    }
    const name = template.slice(i + 1, close);
    if (!shape.test(name)) {
      throw new Error("malformed marker name: " + name);
    }
    if (!(name in values)) {
      throw new Error("no value for marker: " + name);
    }
    if (typeof values[name] !== "string") {
      throw new Error("marker values must be strings");
    }
    out += values[name];
    i = close + 1;
  }
  return out;
}
