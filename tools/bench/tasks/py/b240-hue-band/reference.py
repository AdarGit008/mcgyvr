def hue_band(degrees: int) -> str:
    hue = degrees % 360
    if hue < 60 or hue >= 300:
        return "red"
    return "green" if hue < 180 else "blue"
