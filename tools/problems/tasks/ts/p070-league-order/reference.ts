export function leagueOrder(matches: (string | number)[][]): string[] {
  if (!Array.isArray(matches)) {
    throw new Error("matches must be an array");
  }
  const table = new Map<string, { pts: number; gd: number; gf: number }>();
  const games: { a: string; b: string; ga: number; gb: number }[] = [];
  const side = (team: string) => {
    let row = table.get(team);
    if (row === undefined) {
      row = { pts: 0, gd: 0, gf: 0 };
      table.set(team, row);
    }
    return row;
  };
  for (const entry of matches) {
    if (!Array.isArray(entry) || entry.length !== 4) {
      throw new Error("each match is a 4-item list");
    }
    const [a, b, ga, gb] = entry;
    if (typeof a !== "string" || typeof b !== "string") {
      throw new Error("team names must be strings");
    }
    if (a === b) {
      throw new Error("a team cannot face itself");
    }
    if (
      typeof ga !== "number" ||
      typeof gb !== "number" ||
      !Number.isInteger(ga) ||
      !Number.isInteger(gb) ||
      ga < 0 ||
      gb < 0
    ) {
      throw new Error("goals must be non-negative integers");
    }
    games.push({ a, b, ga, gb });
    const home = side(a);
    const away = side(b);
    home.pts += ga > gb ? 3 : ga === gb ? 1 : 0;
    away.pts += gb > ga ? 3 : ga === gb ? 1 : 0;
    home.gd += ga - gb;
    away.gd += gb - ga;
    home.gf += ga;
    away.gf += gb;
  }
  const groups = new Map<number, string[]>();
  for (const team of table.keys()) {
    const pts = table.get(team)!.pts;
    if (!groups.has(pts)) {
      groups.set(pts, []);
    }
    groups.get(pts)!.push(team);
  }
  const standings: string[] = [];
  for (const pts of [...groups.keys()].sort((x, y) => y - x)) {
    const group = groups.get(pts)!;
    const level = new Set(group);
    const mini = new Map<string, number>();
    for (const team of group) {
      mini.set(team, 0);
    }
    for (const game of games) {
      if (level.has(game.a) && level.has(game.b)) {
        mini.set(game.a, mini.get(game.a)! + (game.ga > game.gb ? 3 : game.ga === game.gb ? 1 : 0));
        mini.set(game.b, mini.get(game.b)! + (game.gb > game.ga ? 3 : game.ga === game.gb ? 1 : 0));
      }
    }
    group.sort((x, y) => {
      if (mini.get(y)! !== mini.get(x)!) {
        return mini.get(y)! - mini.get(x)!;
      }
      const sx = table.get(x)!;
      const sy = table.get(y)!;
      if (sy.gd !== sx.gd) {
        return sy.gd - sx.gd;
      }
      if (sy.gf !== sx.gf) {
        return sy.gf - sx.gf;
      }
      return x < y ? -1 : 1;
    });
    standings.push(...group);
  }
  return standings;
}
