const SHAPES =
  /(?<![A-Z])[A-Z]{2,4}-\d{4,8}(?!\d)|(?<![a-z0-9])vk=[a-z0-9]{6,10}(?![a-z0-9])/g;

export function maskSensitive(note: string): any {
  if (typeof note !== "string") {
    throw new Error("maskSensitive expects a string");
  }
  let badges = 0;
  let vaults = 0;
  const text = note.replace(SHAPES, (found) => {
    if (found.startsWith("vk=")) {
      vaults += 1;
      return "[vault]";
    }
    badges += 1;
    return found.replace(/\d/g, "#");
  });
  return { text, badges, vaults };
}
