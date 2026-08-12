/** The key a list of names is ordered by. */
export function sortKey(name: string): string {
  const cut = name.indexOf(" ");
  if (cut === -1) {
    return name.toLowerCase();
  }
  return (name.slice(cut + 1) + " " + name.slice(0, cut)).toLowerCase();
}
