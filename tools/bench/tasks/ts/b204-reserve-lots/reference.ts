/** Fill orders from the stock lots whose use-by dates fall soonest. */
export function reserveLots(lots: [string, string, number][], orders: [string, number][]): { picks: [string, string, number][]; short: [string, number][] } {
  const stock = lots.map((lot) => ({ id: lot[0], useBy: lot[1], left: lot[2] }));
  stock.sort((a, b) => (a.useBy === b.useBy ? (a.id < b.id ? -1 : 1) : a.useBy < b.useBy ? -1 : 1));
  const picks: [string, string, number][] = [];
  const short: [string, number][] = [];
  for (const [orderId, wanted] of orders) {
    let need = wanted;
    for (const lot of stock) {
      if (need === 0) {
        break;
      }
      const take = Math.min(lot.left, need);
      if (take > 0) {
        lot.left -= take;
        need -= take;
        picks.push([orderId, lot.id, take]);
      }
    }
    if (need > 0) {
      short.push([orderId, need]);
    }
  }
  return { picks, short };
}
