"""The first record of a link setup that departs from the drill."""

VERBS = ("PROBE", "READY", "KEY", "SEAL", "PING", "PONG", "CLOSE")


def audit_link_setup(exchange: list) -> str:
    if not isinstance(exchange, list) or not exchange:
        raise ValueError("the list must be a non-empty list")
    stage = 0
    carried = 0
    for index, record in enumerate(exchange):
        if not isinstance(record, dict):
            raise ValueError("a record must be a mapping")
        side = record.get("side")
        verb = record.get("verb")
        seq = record.get("seq")
        if side not in ("caller", "listener"):
            raise ValueError("a record must come from the caller or the listener")
        if not isinstance(verb, str) or verb not in VERBS:
            raise ValueError("a verb must be one of the seven")
        if isinstance(seq, bool) or not isinstance(seq, int):
            raise ValueError("a seq must be a whole number")
        fault = verb + "@" + str(index + 1)
        if stage == 0:
            if side != "caller" or verb != "PROBE" or seq != 1:
                return fault
            carried = seq
            stage = 1
        elif stage == 1:
            if side != "listener" or verb != "READY" or seq != carried:
                return fault
            stage = 2
        elif stage == 2:
            if side != "caller" or verb != "KEY" or seq != carried + 1:
                return fault
            carried = seq
            stage = 3
        elif stage == 3:
            if side != "listener" or verb != "SEAL" or seq != carried:
                return fault
            stage = 4
        elif stage == 4:
            if side != "caller" or seq != carried + 1:
                return fault
            if verb == "PING":
                carried = seq
                stage = 5
            elif verb == "CLOSE":
                carried = seq
                stage = 6
            else:
                return fault
        elif stage == 5:
            if side != "listener" or verb != "PONG" or seq != carried:
                return fault
            stage = 4
        elif stage == 6:
            if side != "listener" or verb != "CLOSE" or seq != carried:
                return fault
            stage = 7
        else:
            return fault
    return "" if stage == 7 else "short"
