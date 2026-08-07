def unmuted_alerts(alerts):
    seen = set()
    peaks = {}
    for alert in alerts:
        ident = alert["id"]
        if ident in seen:
            raise ValueError("two alerts share an id")
        seen.add(ident)
        severity = alert["severity"]
        if not isinstance(severity, int) or isinstance(severity, bool) or severity < 1:
            raise ValueError("severity must be a positive integer")
        resource = alert["resource"]
        if severity > peaks.get(resource, 0):
            peaks[resource] = severity
    unmuted = [
        alert for alert in alerts if alert["severity"] == peaks[alert["resource"]]
    ]
    unmuted.sort(key=lambda alert: (-alert["severity"], alert["id"]))
    return [alert["id"] for alert in unmuted]
