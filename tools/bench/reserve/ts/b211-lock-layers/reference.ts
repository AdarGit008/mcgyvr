/** Fold configuration layers, honouring the locks declared along the way. */

interface Layer {
  set: Record<string, string>;
  drop: string[];
  lock: string[];
}

export function resolveLayers(layers: Layer[]): Record<string, string> {
  const settled: Record<string, string> = {};
  const frozen = new Set<string>();
  for (const layer of layers) {
    for (const [name, value] of Object.entries(layer.set)) {
      if (!frozen.has(name)) {
        settled[name] = value;
      }
    }
    for (const name of layer.drop) {
      if (!frozen.has(name)) {
        delete settled[name];
      }
    }
    for (const name of layer.lock) {
      frozen.add(name);
    }
  }
  return settled;
}
