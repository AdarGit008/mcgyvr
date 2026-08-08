function isMapping(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function applyLayer(
  base: Record<string, unknown>,
  layer: Record<string, unknown>,
): void {
  for (const [key, incoming] of Object.entries(layer)) {
    if (incoming === null) {
      delete base[key];
    } else if (isMapping(incoming)) {
      const existing = base[key];
      const branch: Record<string, unknown> = isMapping(existing)
        ? existing
        : {};
      base[key] = branch;
      applyLayer(branch, incoming);
    } else {
      base[key] = incoming;
    }
  }
}

export function layerConfigs(
  layers: Array<Record<string, unknown>>,
): Record<string, unknown> {
  if (!Array.isArray(layers)) {
    throw new Error("layerConfigs expects a list of layers");
  }
  const result: Record<string, unknown> = {};
  for (const layer of layers) {
    if (!isMapping(layer)) {
      throw new Error("every layer must be a mapping");
    }
    applyLayer(result, layer);
  }
  return result;
}
