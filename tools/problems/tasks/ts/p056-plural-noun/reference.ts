export function pluralNoun(word: string): string {
  if (typeof word !== "string") {
    throw new Error("pluralNoun expects a string");
  }
  if (word === "" || !/^[a-z]+$/.test(word)) {
    throw new Error("expected lowercase letters a-z only");
  }
  const irregular: Record<string, string> = {
    child: "children",
    person: "people",
    foot: "feet",
    mouse: "mice",
    sheep: "sheep",
  };
  if (word in irregular) {
    return irregular[word];
  }
  if (/(?:s|x|z|ch|sh)$/.test(word)) {
    return word + "es";
  }
  if (word.length >= 2 && word.endsWith("y") && !"aeiou".includes(word[word.length - 2])) {
    return word.slice(0, -1) + "ies";
  }
  if (word.endsWith("fe")) {
    return word.slice(0, -2) + "ves";
  }
  if (word.endsWith("f")) {
    return word.slice(0, -1) + "ves";
  }
  return word + "s";
}
