/** Which entries on a branching sheet were owed, spurious or missing. */
export function auditBranchReplies(sheet: Record<string, unknown>): Record<string, unknown> {
  const mapping = (value: unknown): boolean =>
    value !== null && typeof value === "object" && !Array.isArray(value);
  if (!mapping(sheet)) throw new Error("the sheet must be a mapping");
  const items = sheet.items;
  if (!Array.isArray(items) || items.length === 0) {
    throw new Error("the items must be a non-empty list");
  }
  const tags: string[] = [];
  const guards: Array<{ tag: string; is: string } | null> = [];
  for (const item of items) {
    if (!mapping(item)) throw new Error("an item must be a mapping");
    const tag = (item as Record<string, unknown>).tag;
    if (typeof tag !== "string" || tag.length === 0) {
      throw new Error("an item needs a non-empty tag");
    }
    if (tags.includes(tag)) throw new Error("two items carry the same tag");
    const when = (item as Record<string, unknown>).when;
    if (when === undefined || when === null) {
      guards.push(null);
    } else {
      if (!mapping(when)) throw new Error("a when must be a mapping");
      const on = (when as Record<string, unknown>).tag;
      const is = (when as Record<string, unknown>).is;
      if (typeof on !== "string" || !tags.includes(on)) {
        throw new Error("a when must lean on an item standing earlier");
      }
      if (typeof is !== "string" || is.length === 0) {
        throw new Error("a when needs a non-empty is");
      }
      guards.push({ tag: on, is });
    }
    tags.push(tag);
  }
  const given = sheet.given;
  if (!mapping(given)) throw new Error("the given answers must be a mapping");
  for (const [tag, answer] of Object.entries(given as Record<string, unknown>)) {
    if (!tags.includes(tag)) throw new Error("an answer names no item of the sheet");
    if (typeof answer !== "string" || answer.length === 0) {
      throw new Error("an answer must be a non-empty string");
    }
  }

  const answers = given as Record<string, string>;
  const owed = new Map<string, boolean>();
  const due: string[] = [];
  const extra: string[] = [];
  const gap: string[] = [];
  for (let index = 0; index < tags.length; index++) {
    const tag = tags[index];
    const guard = guards[index];
    const settled =
      guard === null
        ? true
        : (owed.get(guard.tag) as boolean) && answers[guard.tag] === guard.is;
    owed.set(tag, settled);
    const answered = Object.prototype.hasOwnProperty.call(answers, tag);
    if (settled) {
      due.push(tag);
      if (!answered) gap.push(tag);
    } else if (answered) {
      extra.push(tag);
    }
  }
  return { due, extra, gap };
}
