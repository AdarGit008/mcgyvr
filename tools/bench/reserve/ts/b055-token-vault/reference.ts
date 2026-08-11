type Vault = Record<string, [string, number]>;

export function tokenSave(vault: Vault, name: string, value: string, now: number, ttl: number): void {
  if (typeof name !== "string" || name.length === 0) {
    throw new Error("token name must be a non-empty string");
  }
  if (!Number.isInteger(now) || !Number.isInteger(ttl) || ttl <= 0) {
    throw new Error("now must be an integer and ttl a positive integer");
  }
  vault[name] = [value, now + ttl];
}

export function tokenFetch(vault: Vault, name: string, now: number): string | null {
  const held = vault[name];
  if (held === undefined) {
    return null;
  }
  if (now >= held[1]) {
    delete vault[name];
    return null;
  }
  return held[0];
}
