export function aliasResolve(
  aliases: Record<string, string>,
  name: string,
): string {
  if (Object.prototype.hasOwnProperty.call(aliases, name)) {
    return aliases[name];
  }
  return name;
}

export function aliasNames(aliases: Record<string, string>): string[] {
  return Object.keys(aliases).sort();
}
