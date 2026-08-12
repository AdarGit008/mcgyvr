/** Run a lift that sweeps on in its heading until nothing lies ahead. */
export function runElevator(top: number, calls: number[][]): { stops: number[]; travel: number } {
  if (calls.some((call) => call[1] < 1 || call[1] > top)) {
    throw new Error("call floor outside the building");
  }
  const waiting: number[] = [];
  const stops: number[] = [];
  let floor = 1;
  let up = true;
  let travel = 0;
  for (let time = 0; stops.length < calls.length; time++) {
    for (const call of calls.filter((c) => c[0] === time)) {
      waiting.push(call[1]);
    }
    while (waiting.includes(floor)) {
      waiting.splice(waiting.indexOf(floor), 1);
      stops.push(floor);
    }
    if (waiting.length > 0) {
      if (!waiting.some((want) => (up ? want > floor : want < floor))) {
        up = !up;
      }
      floor += up ? 1 : -1;
      travel++;
    }
  }
  return { stops, travel };
}
