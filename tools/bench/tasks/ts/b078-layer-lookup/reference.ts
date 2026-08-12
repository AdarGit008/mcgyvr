export function configValue(layers: string[], name: string): string | null {
  if (typeof name !== "string" || name.length === 0) {
    throw new Error("name must be a non-empty string");
  }
  let found: string | null = null;
  for (const layer of layers) {
    if (typeof layer !== "string") {
      throw new Error("each layer must be a string");
    }
    for (const raw of layer.split("\n")) {
      const line = raw.trim();
      if (line.length === 0 || line.startsWith("#")) continue;
      if (line.startsWith("!")) {
        if (line.slice(1).trim() === name) found = null;
        continue;
      }
      const eq = line.indexOf("=");
      if (eq <= 0) throw new Error("malformed line: " + raw);
      if (line.slice(0, eq).trim() === name) found = line.slice(eq + 1).trim();
    }
  }
  return found;
}
