def _whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _greatest_common(a, b):
    left, right = abs(a), abs(b)
    while right != 0:
        left, right = right, left % right
    return left


def _inverse(value, span):
    if span == 1:
        return 0
    older, newer = span, value % span
    coefficient_older, coefficient_newer = 0, 1
    while newer != 0:
        quotient = older // newer
        older, newer = newer, older - quotient * newer
        coefficient_older, coefficient_newer = (
            coefficient_newer,
            coefficient_older - quotient * coefficient_newer,
        )
    return coefficient_older % span


def _check_start(value):
    if not _whole(value) or value < 0 or value > 1000000:
        raise ValueError("a start must be a whole number from 0 through 1000000")


def _check_stride(value):
    if not _whole(value) or value < 1 or value > 100000:
        raise ValueError("a stride must be a whole number from 1 through 100000")


def meeting_points(
    start_a: int, stride_a: int, start_b: int, stride_b: int, count: int
) -> list:
    _check_start(start_a)
    _check_start(start_b)
    _check_stride(stride_a)
    _check_stride(stride_b)
    if not _whole(count) or count < 0 or count > 20:
        raise ValueError("count must be a whole number from 0 through 20")

    common = _greatest_common(stride_a, stride_b)
    if (start_b - start_a) % common != 0:
        return []
    stride = (stride_a // common) * stride_b
    reduced = stride_b // common
    shift = ((start_b - start_a) // common) % reduced
    step = (shift * _inverse(stride_a // common, reduced)) % reduced
    landing = (start_a + stride_a * step) % stride

    threshold = max(start_a, start_b)
    if landing < threshold:
        gap = threshold - landing
        jumps = -((-gap) // stride)
        landing += jumps * stride

    return [landing + index * stride for index in range(count)]
