/** Canonical account handles from free-form display names. */

export function normalizeHandle(raw: string): string {
  if (typeof raw !== "string") {
    throw new Error("normalizeHandle expects a string");
  }
  const collapsed = raw.trim().toLowerCase().replace(/[ _-]+/g, "-");
  if (collapsed.length === 0) {
    throw new Error("handle is empty");
  }
  if (!/^[a-z0-9-]+$/.test(collapsed)) {
    throw new Error("handle has an illegal character");
  }
  if (collapsed.startsWith("-") || collapsed.endsWith("-")) {
    throw new Error("handle may not begin or end with a hyphen");
  }
  if (collapsed.length < 3 || collapsed.length > 20) {
    throw new Error("handle length out of range");
  }
  return collapsed;
}
