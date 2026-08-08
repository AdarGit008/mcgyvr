const SPAN = /^(0|[1-9]\d*)?\.\.(0|[1-9]\d*)?((?:!(?:0|[1-9]\d*))*)$/;

export function intersectBuildSpans(spans: string[]): string {
  if (!Array.isArray(spans) || spans.length === 0) {
    throw new Error("at least one span is required");
  }
  let lo: number | null = null;
  let hi: number | null = null;
  const strikes = new Set<number>();
  for (const span of spans) {
    if (typeof span !== "string") {
      throw new Error("span must be a string");
    }
    const m = SPAN.exec(span);
    if (m === null) {
      throw new Error(`malformed span: ${span}`);
    }
    const spanLo = m[1] === undefined ? null : Number(m[1]);
    const spanHi = m[2] === undefined ? null : Number(m[2]);
    if (spanLo !== null && spanHi !== null && spanLo > spanHi) {
      throw new Error(`reversed limits: ${span}`);
    }
    const marks = m[3] === "" ? [] : m[3].slice(1).split("!").map(Number);
    for (const struck of marks) {
      if ((spanLo !== null && struck < spanLo) || (spanHi !== null && struck > spanHi)) {
        throw new Error(`strike outside its span: ${span}`);
      }
      strikes.add(struck);
    }
    if (spanLo !== null) {
      lo = lo === null ? spanLo : Math.max(lo, spanLo);
    }
    if (spanHi !== null) {
      hi = hi === null ? spanHi : Math.min(hi, spanHi);
    }
  }
  const survivors = new Set(
    [...strikes].filter(
      (struck) => (lo === null || struck >= lo) && (hi === null || struck <= hi),
    ),
  );
  while (lo !== null && survivors.has(lo)) {
    survivors.delete(lo);
    lo += 1;
  }
  while (hi !== null && survivors.has(hi)) {
    survivors.delete(hi);
    hi -= 1;
  }
  if (lo !== null && hi !== null && lo > hi) {
    return "empty";
  }
  const tail = [...survivors]
    .sort((a, b) => a - b)
    .map((struck) => `!${struck}`)
    .join("");
  return `${lo === null ? "" : lo}..${hi === null ? "" : hi}${tail}`;
}
