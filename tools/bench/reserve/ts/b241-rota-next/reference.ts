export function rotaNext(rota: string[], name: string): string {
  const at = rota.indexOf(name);
  if (at === -1) {
    return name;
  }
  return rota[(at + 1) % rota.length];
}
