export function unmutedAlerts(
  alerts: Array<{ id: string; resource: string; severity: number }>,
): string[] {
  const seen = new Set<string>();
  const peaks = new Map<string, number>();
  for (const alert of alerts) {
    if (seen.has(alert.id)) {
      throw new Error("two alerts share an id");
    }
    seen.add(alert.id);
    if (!Number.isInteger(alert.severity) || alert.severity < 1) {
      throw new Error("severity must be a positive integer");
    }
    const peak = peaks.get(alert.resource) ?? 0;
    if (alert.severity > peak) {
      peaks.set(alert.resource, alert.severity);
    }
  }
  return alerts
    .filter((alert) => alert.severity === peaks.get(alert.resource))
    .sort((a, b) =>
      a.severity !== b.severity
        ? b.severity - a.severity
        : a.id < b.id
          ? -1
          : 1,
    )
    .map((alert) => alert.id);
}
