def tint_mix(volume_a: int, strength_a: int, volume_b: int, strength_b: int) -> int:
    total = volume_a + volume_b
    if total == 0:
        return 0
    return (volume_a * strength_a + volume_b * strength_b) // total
