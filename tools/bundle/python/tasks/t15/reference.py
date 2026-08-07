def convert_temps(values: list[float], mode: str) -> list[int]:
    """Convert Celsius values to the target scale, rounded to ints."""
    if mode == "fahrenheit":
        return [round(v * 9 / 5 + 32) for v in values]
    if mode == "kelvin":
        return [round(v + 273.15) for v in values]
    raise ValueError(f"unknown mode: {mode!r}")


def celsius_to_fahrenheit_rounded(values: list[float]) -> list[int]:
    """Celsius -> Fahrenheit, rounded."""
    return convert_temps(values, "fahrenheit")


def celsius_to_kelvin_rounded(values: list[float]) -> list[int]:
    """Celsius -> Kelvin, rounded."""
    return convert_temps(values, "kelvin")
