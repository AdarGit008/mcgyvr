/** Normalize a locale tag to canonical separators and letter case. */

function titleCase(segment: string): string {
  return segment[0].toUpperCase() + segment.slice(1).toLowerCase();
}

export function normalizeLocaleTag(tag: string): string {
  if (typeof tag !== "string") {
    throw new Error("normalizeLocaleTag expects a string");
  }
  if (tag === "") {
    throw new Error("empty locale tag");
  }
  const segments = tag.split(/[-_]/);
  if (segments.some((segment) => segment === "")) {
    throw new Error("empty subtag");
  }
  let core = segments;
  let privateUse: string[] | null = null;
  for (let position = 0; position < segments.length; position += 1) {
    if (segments[position].toLowerCase() === "x") {
      core = segments.slice(0, position);
      privateUse = segments.slice(position + 1);
      break;
    }
  }
  if (core.length === 0) {
    throw new Error("missing language subtag");
  }
  if (core.length > 4) {
    throw new Error("too many subtags before the private-use part");
  }
  if (!/^[A-Za-z]{2,3}$/.test(core[0])) {
    throw new Error("language subtag must be 2 or 3 letters");
  }
  const normalized: string[] = [core[0].toLowerCase()];
  let index = 1;
  if (index < core.length && /^[A-Za-z]{4}$/.test(core[index])) {
    normalized.push(titleCase(core[index]));
    index += 1;
  }
  if (index < core.length && /^(?:[A-Za-z]{2}|[0-9]{3})$/.test(core[index])) {
    normalized.push(core[index].toUpperCase());
    index += 1;
  }
  if (index < core.length && /^[A-Za-z0-9]{5,8}$/.test(core[index])) {
    normalized.push(core[index].toLowerCase());
    index += 1;
  }
  if (index < core.length) {
    throw new Error("subtag fits no slot in order");
  }
  if (privateUse !== null) {
    if (privateUse.length === 0) {
      throw new Error("x marker with nothing after it");
    }
    normalized.push("x");
    for (const segment of privateUse) {
      if (!/^[A-Za-z0-9]{1,8}$/.test(segment)) {
        throw new Error("bad private-use subtag");
      }
      normalized.push(segment.toLowerCase());
    }
  }
  return normalized.join("-");
}
