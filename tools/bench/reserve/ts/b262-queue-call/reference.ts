export function queueCall(
  tickets: string[],
  withdrawn: string[],
  called: string,
): string | null {
  const at = tickets.indexOf(called);
  for (let i = at + 1; i < tickets.length; i += 1) {
    if (!withdrawn.includes(tickets[i])) {
      return tickets[i];
    }
  }
  return null;
}
