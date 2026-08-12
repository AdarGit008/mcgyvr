/** Serialize a preset's dial positions as sorted name=value pairs. */
export function packDials(dials: Record<string, number>): string {
  if (typeof dials !== "object" || dials === null || Array.isArray(dials)) {
    throw new Error("packDials expects a plain mapping");
  }
  const parts: string[] = [];
  for (const name of Object.keys(dials).sort()) {
    if (name === "" || name.includes("=") || name.includes(";")) throw new Error("bad dial name");
    const position = dials[name];
    if (!Number.isInteger(position) || position < 0) throw new Error("bad dial position");
    parts.push(name + "=" + String(position));
  }
  return parts.join(";");
}
