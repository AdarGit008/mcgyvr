from solution import code_case


def rejects(value):
    try:
        code_case(value)
    except Exception:
        return True
    return False


assert code_case("  ab-12 ") == "AB-12", "trimmed and raised"
assert code_case("xy9") == "XY9", "letters raised, digits alone"
assert code_case("a b") == "A B", "an inner space survives"
assert code_case("ALREADY") == "ALREADY", "already upper"
assert rejects(""), "an empty code is rejected"
assert rejects("   "), "spaces alone are rejected"
print("ok")
