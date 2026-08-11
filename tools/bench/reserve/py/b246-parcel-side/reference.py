def parcel_girth(width: int, height: int) -> int:
    return 2 * (width + height)


def parcel_oversize(length: int, width: int, height: int, limit: int) -> bool:
    return length + parcel_girth(width, height) > limit
