from solution import wave_count

assert wave_count([1, 3, 2]) == 1, "up then down is one change"
assert wave_count([1, 2, 3]) == 0, "a steady rise never changes"
assert wave_count([1, 3, 2, 4]) == 2, "two changes"
assert wave_count([]) == 0, "no readings at all"
assert wave_count([5, 5, 5]) == 0, "level ground changes nothing"
assert wave_count([1, 3, 3, 2]) == 1, "a level step does not break it"
print("ok")
