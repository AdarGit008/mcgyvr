WORDS = ("is", "not", "in")

MISSING = object()


def _record(value):
    return isinstance(value, dict)


def _text(value):
    return isinstance(value, str) and value != ""


def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def pick_flag_variant(flag, subject) -> dict:
    if not _record(flag) or "rules" not in flag or "fallback" not in flag:
        raise ValueError("a flag must be a record carrying rules and fallback")
    if not isinstance(flag["rules"], list):
        raise ValueError("rules must be a list")
    if not _text(flag["fallback"]):
        raise ValueError("fallback must be a non-empty string")
    if not _record(subject) or "traits" not in subject or "bucket" not in subject:
        raise ValueError("a subject must be a record carrying traits and bucket")
    if not _record(subject["traits"]):
        raise ValueError("traits must be a record")
    for value in subject["traits"].values():
        if not isinstance(value, str):
            raise ValueError("every trait must hold a string")
    bucket = subject["bucket"]
    if not _whole(bucket) or bucket < 0 or bucket > 99:
        raise ValueError("bucket must be a whole number from 0 to 99")

    rules = []
    for raw in flag["rules"]:
        if not _record(raw) or "match" not in raw or "split" not in raw:
            raise ValueError("a rule must be a record carrying match and split")
        if not isinstance(raw["match"], list):
            raise ValueError("match must be a list")
        tests = []
        for test in raw["match"]:
            if not isinstance(test, list) or len(test) != 3:
                raise ValueError("a test must be a three-element list")
            trait, word, value = test
            if not _text(trait):
                raise ValueError("a trait name must be a non-empty string")
            if word not in WORDS:
                raise ValueError("a test word must be is, not or in")
            if word == "in":
                if not isinstance(value, list) or not value:
                    raise ValueError("an in test needs a non-empty list")
                for option in value:
                    if not isinstance(option, str):
                        raise ValueError("an in test lists strings")
            elif not isinstance(value, str):
                raise ValueError("an is or not test compares against a string")
            tests.append((trait, word, value))
        split_raw = raw["split"]
        if not isinstance(split_raw, list) or not split_raw:
            raise ValueError("split must be a non-empty list")
        split = []
        named = set()
        total = 0
        for entry in split_raw:
            if not isinstance(entry, list) or len(entry) != 2:
                raise ValueError("a split entry must be a two-element list")
            variant, share = entry
            if not _text(variant):
                raise ValueError("a variant must be a non-empty string")
            if variant in named:
                raise ValueError("a split names " + variant + " twice")
            named.add(variant)
            if not _whole(share) or share < 0:
                raise ValueError("a share must be a whole number of zero or more")
            total += share
            split.append((variant, share))
        if total != 100:
            raise ValueError("the shares of a split must add up to 100")
        rules.append((tests, split))

    traits = subject["traits"]

    def holds(test):
        trait, word, value = test
        carried = traits.get(trait, MISSING)
        if word == "is":
            return carried is not MISSING and carried == value
        if word == "in":
            return carried is not MISSING and carried in value
        return carried is MISSING or carried != value

    for index, (tests, split) in enumerate(rules):
        if not all(holds(test) for test in tests):
            continue
        running = 0
        for variant, share in split:
            running += share
            if running > bucket:
                return {"variant": variant, "rule": index}
    return {"variant": flag["fallback"], "rule": -1}
