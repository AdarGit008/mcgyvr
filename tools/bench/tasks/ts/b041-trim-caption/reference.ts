/** Shorten a caption to a character budget without splitting a word. */
export function trimCaption(text: string, limit: number): string {
  if (typeof text !== "string") {
    throw new Error("trimCaption expects a string");
  }
  if (!Number.isInteger(limit) || limit < 1) {
    throw new Error("limit must be a positive integer");
  }
  if (text.length <= limit) {
    return text;
  }
  let cut = text.slice(0, limit - 1);
  if (text[limit - 1] !== " " && cut.includes(" ")) {
    cut = cut.slice(0, cut.lastIndexOf(" "));
  }
  while (cut.endsWith(" ")) {
    cut = cut.slice(0, -1);
  }
  return cut + "…";
}
