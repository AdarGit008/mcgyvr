/** The KEY=VALUE pairs of a config file. */
export function parseConfig(text: string): Record<string, string> {
  // A null-prototype object: a "__proto__" key becomes data, not an assignment
  // to the prototype chain.
  const config: Record<string, string> = Object.create(null);
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed === "" || trimmed.startsWith("#")) {
      continue;
    }
    const separator = trimmed.indexOf("=");
    if (separator === -1) {
      throw new Error(`line has no '=': ${line}`);
    }
    const key = trimmed.slice(0, separator).trim();
    if (key === "") {
      throw new Error(`line has an empty key: ${line}`);
    }
    config[key] = trimmed.slice(separator + 1).trim();
  }
  return config;
}
