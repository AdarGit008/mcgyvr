from solution import intersect_build_spans

assert intersect_build_spans(["5..20", "10..30"]) == "10..20", "limits tighten both ways"
assert intersect_build_spans(["..15!7", "3.."]) == "3..15!7", "strike inside survives"
assert intersect_build_spans(["0..9!9", "5.."]) == "5..8", "strike on the upper limit shrinks it"
assert intersect_build_spans(["5..9!5!6", ".."]) == "7..9", "limit cascades past consecutive strikes"
assert intersect_build_spans(["2..8!4", "4..10"]) == "5..8", "tightening turns a strike into a limit move"
assert intersect_build_spans(["5..6!5!6"]) == "empty", "everything struck is empty"
assert intersect_build_spans(["10..20", "30..40"]) == "empty", "disjoint spans are empty"
assert intersect_build_spans([".."]) == "..", "the unlimited span is its own canonical form"
assert intersect_build_spans(["..!3", ".."]) == "..!3", "an unlimited span can still strike"
assert intersect_build_spans(["0..50!7", "..30!7!7"]) == "0..30!7", "duplicate strikes are written once"
assert intersect_build_spans(["1..100!40", "50.."]) == "50..100", "a strike below the final limits vanishes"


def rejects(spans):
    try:
        intersect_build_spans(spans)
    except ValueError:
        return True
    return False


assert rejects(["5..3"]), "reversed limits are rejected"
assert rejects(["05..9"]), "a leading zero is rejected"
assert rejects(["5..9!12"]), "a strike outside its span is rejected"
assert rejects(["5-9"]), "a malformed span is rejected"
assert rejects(["5..9!!3"]), "a bare double bang is rejected"
assert rejects([]), "an empty list is rejected"
assert rejects([7]), "a non-string span is rejected"
print("ok")
