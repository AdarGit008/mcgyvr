/** Swap macro references for their values, following values in turn. */

function expandInto(
  text: string,
  macros: Record<string, string>,
  active: string[],
): string {
  const reference = /\$\(([a-z0-9]+)(?::([^()]*))?\)/g;
  return text.replace(
    reference,
    (whole: string, name: string, fallback?: string) => {
      if (active.includes(name)) {
        throw new Error("macro cycle through " + name);
      }
      if (name in macros) {
        return expandInto(macros[name], macros, active.concat(name));
      }
      return fallback === undefined ? "" : fallback;
    },
  );
}

export function expandMacro(text: string, macros: Record<string, string>): string {
  return expandInto(text, macros, []);
}
