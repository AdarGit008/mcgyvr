const FAMILIES = ["upright", "oblong", "square"];

function whole(value: unknown, least: number): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= least;
}

function isRecord(value: unknown): boolean {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function groupPhotoRows(photos: any[], sheet: any): any[] {
  if (!Array.isArray(photos) || photos.length === 0) {
    throw new Error("photos must be a list holding at least one picture");
  }
  if (!isRecord(sheet)) {
    throw new Error("sheet must be a record");
  }
  if (!whole(sheet.width, 1)) {
    throw new Error("sheet.width must be a whole number above nought");
  }
  if (!whole(sheet.band, 1)) {
    throw new Error("sheet.band must be a whole number above nought");
  }
  if (!whole(sheet.gap, 0)) {
    throw new Error("sheet.gap must be a whole number of nought or more");
  }

  const seen = new Set<string>();
  const kept: { tag: string; family: string; span: number }[] = [];
  for (const photo of photos) {
    if (!isRecord(photo)) {
      throw new Error("each photo must be a record");
    }
    if (typeof photo.tag !== "string" || photo.tag.length === 0) {
      throw new Error("tag must be a non-empty string");
    }
    if (seen.has(photo.tag)) {
      throw new Error(`two photos answer to the tag ${photo.tag}`);
    }
    seen.add(photo.tag);
    if (!whole(photo.wide, 1) || !whole(photo.high, 1)) {
      throw new Error("wide and high must be whole numbers above nought");
    }
    const span = Math.floor((photo.wide * sheet.band) / photo.high);
    if (span === 0) {
      throw new Error(`${photo.tag} prints to nothing at this band height`);
    }
    if (span > sheet.width) {
      throw new Error(`${photo.tag} is too wide to lie on a band by itself`);
    }
    const family =
      photo.high > photo.wide
        ? "upright"
        : photo.wide > photo.high
          ? "oblong"
          : "square";
    kept.push({ tag: photo.tag, family, span });
  }

  const bands: any[] = [];
  for (const family of FAMILIES) {
    let tags: string[] = [];
    let run = 0;
    const close = () => {
      if (tags.length > 0) {
        bands.push({ family, tags, run, spare: sheet.width - run });
        tags = [];
        run = 0;
      }
    };
    for (const member of kept) {
      if (member.family !== family) {
        continue;
      }
      const cost = tags.length === 0 ? member.span : sheet.gap + member.span;
      if (run + cost <= sheet.width) {
        run += cost;
        tags.push(member.tag);
      } else {
        close();
        run = member.span;
        tags = [member.tag];
      }
    }
    close();
  }
  return bands;
}
