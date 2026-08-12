export function crustSlice(name: string): string {
  const cut = name.lastIndexOf(".");
  if (cut <= 0) {
    return name;
  }
  return name.slice(0, cut);
}
