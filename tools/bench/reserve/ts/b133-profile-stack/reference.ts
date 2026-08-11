/** Resolve layered configuration profiles that extend one another. */

function isLayer(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function mergeLayers(
  base: Record<string, unknown>,
  override: Record<string, unknown>,
): Record<string, unknown> {
  if (!isLayer(base) || !isLayer(override)) {
    throw new Error("mergeLayers expects two mappings");
  }
  const merged: Record<string, unknown> = {};
  for (const key of Object.keys(base)) {
    merged[key] = base[key];
  }
  for (const key of Object.keys(override)) {
    const ours = merged[key];
    const theirs = override[key];
    if (isLayer(ours) && isLayer(theirs)) {
      merged[key] = mergeLayers(ours, theirs);
    } else {
      merged[key] = theirs;
    }
  }
  return merged;
}

export function resolveProfile(
  name: string,
  profiles: Record<string, unknown>,
): Record<string, unknown> {
  if (!isLayer(profiles)) {
    throw new Error("profiles must be a mapping");
  }
  function resolve(target: string, trail: string[]): Record<string, unknown> {
    if (trail.includes(target)) {
      throw new Error(`extends cycle at: ${target}`);
    }
    const profile = profiles[target];
    if (profile === undefined) {
      throw new Error(`unknown profile: ${target}`);
    }
    if (!isLayer(profile)) {
      throw new Error(`profile is not a mapping: ${target}`);
    }
    const parents = profile.extends ?? [];
    if (!Array.isArray(parents)) {
      throw new Error(`extends must be a list: ${target}`);
    }
    const settings = profile.settings ?? {};
    if (!isLayer(settings)) {
      throw new Error(`settings must be a mapping: ${target}`);
    }
    let resolved: Record<string, unknown> = {};
    for (const parent of parents) {
      if (typeof parent !== "string") {
        throw new Error(`extends entries must be strings: ${target}`);
      }
      resolved = mergeLayers(resolved, resolve(parent, [...trail, target]));
    }
    return mergeLayers(resolved, settings);
  }
  return resolve(name, []);
}
