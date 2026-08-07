/** The track each span is drawn on. */
export function assignTrackColumns(
  spans: { label: string; first: number; last: number }[],
): number[] {
  if (!Array.isArray(spans)) {
    throw new Error("spans must be a list");
  }
  const labels = new Set<string>();
  for (const span of spans) {
    if (typeof span !== "object" || span === null || Array.isArray(span)) {
      throw new Error("every span must be a mapping");
    }
    if (typeof span.label !== "string" || span.label.length === 0) {
      throw new Error("every span needs a non-empty label");
    }
    if (!Number.isInteger(span.first) || !Number.isInteger(span.last)) {
      throw new Error(`span ${span.label} has rows that are not whole numbers`);
    }
    if (span.first < 0) {
      throw new Error(`span ${span.label} starts before row zero`);
    }
    if (span.last < span.first) {
      throw new Error(`span ${span.label} ends before it starts`);
    }
    if (labels.has(span.label)) {
      throw new Error(`two spans share the label ${span.label}`);
    }
    labels.add(span.label);
  }

  const placed: { first: number; last: number; track: number }[] = [];
  const tracks: number[] = [];
  for (const span of spans) {
    const busy = new Set<number>();
    for (const other of placed) {
      if (span.first <= other.last && span.last >= other.first) {
        busy.add(other.track);
      }
    }
    let track = 0;
    while (busy.has(track)) {
      track += 1;
    }
    placed.push({ first: span.first, last: span.last, track });
    tracks.push(track);
  }
  return tracks;
}
