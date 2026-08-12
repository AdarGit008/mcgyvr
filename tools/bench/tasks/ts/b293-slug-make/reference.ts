export function slugWord(word: string): string {
  return word.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function slugMake(phrase: string): string {
  const parts: string[] = [];
  for (const word of phrase.split(/\s+/)) {
    const slug = slugWord(word);
    if (slug !== "") {
      parts.push(slug);
    }
  }
  return parts.join("-");
}
