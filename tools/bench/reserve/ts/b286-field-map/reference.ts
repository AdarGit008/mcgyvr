export function fieldMap(entries: string[]): Record<string, string> {
  const settings: Record<string, string> = {};
  for (const entry of entries) {
    const cut = entry.indexOf("=");
    if (cut === -1) {
      continue;
    }
    settings[entry.slice(0, cut)] = entry.slice(cut + 1);
  }
  return settings;
}
