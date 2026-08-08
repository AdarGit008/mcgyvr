/** Where a play order crowds one artist too closely. */
export function auditArtistGaps(
  playlist: string[],
  spacing: number,
): Record<string, unknown>[] {
  if (!Array.isArray(playlist) || playlist.length === 0) {
    throw new Error("the playlist must be a list with at least one track");
  }
  if (
    typeof spacing !== "number" ||
    !Number.isInteger(spacing) ||
    spacing < 0
  ) {
    throw new Error("the spacing must be a whole number of zero or more");
  }

  const report: Record<string, unknown>[] = [];
  const lastSeen = new Map<string, number>();
  for (let at = 0; at < playlist.length; at++) {
    const artist = playlist[at];
    if (typeof artist !== "string" || artist.length === 0) {
      throw new Error(`the entry at ${at} is not an artist name`);
    }
    const before = lastSeen.get(artist);
    if (before !== undefined) {
      const between = at - before - 1;
      if (between < spacing) {
        report.push({ artist, at, between });
      }
    }
    lastSeen.set(artist, at);
  }
  return report;
}
