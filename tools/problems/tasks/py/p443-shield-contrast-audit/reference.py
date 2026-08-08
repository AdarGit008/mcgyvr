METALS = frozenset({"or", "argent"})
COLOURS = frozenset({"gules", "azure", "sable", "vert", "purpure"})


def _class_of(tincture) -> str:
    if tincture in METALS:
        return "metal"
    if tincture in COLOURS:
        return "colour"
    raise ValueError(f"unknown tincture {tincture}")


def audit_shield_contrast(shields: list) -> list:
    """Which figures fail to stand out from the field behind them."""
    if not isinstance(shields, list):
        raise ValueError("shields must be a list")
    labels = set()
    report = []
    for shield in shields:
        label = shield.get("label")
        if not isinstance(label, str) or label == "":
            raise ValueError("every shield needs a non-empty label")
        if label in labels:
            raise ValueError(f"two shields share the label {label}")
        labels.add(label)

        field = shield["field"]
        if not isinstance(field, list) or not 1 <= len(field) <= 2:
            raise ValueError(f"the field of {label} is not one or two tinctures")
        field_classes = [_class_of(each) for each in field]

        borne = set()
        unsound = []
        for charge in shield["charges"]:
            figure = charge["figure"]
            if figure in borne:
                raise ValueError(f"{label} bears {figure} twice")
            borne.add(figure)
            own = _class_of(charge["tincture"])
            shares_name = charge["tincture"] in field
            contrasts = any(each != own for each in field_classes)
            if shares_name or not contrasts:
                unsound.append(figure)
        if unsound:
            report.append({"label": label, "unsound": unsound})
    return report
