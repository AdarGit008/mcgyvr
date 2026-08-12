from solution import normalize_locale_tag

assert normalize_locale_tag("en") == "en", "bare language stays"
assert normalize_locale_tag("EN_us") == "en-US", "case and separator normalize"
assert normalize_locale_tag("zh-hans-cn") == "zh-Hans-CN", "script and region recase"
assert normalize_locale_tag("sr_lATN_rs") == "sr-Latn-RS", "mixed-case script recases"
assert normalize_locale_tag("es-419") == "es-419", "digit region kept as-is"
assert normalize_locale_tag("yue") == "yue", "three-letter language"
assert normalize_locale_tag("sl-rozaj") == "sl-rozaj", "variant without script or region"
assert normalize_locale_tag("AZ-LATN-X-OLD") == "az-Latn-x-old", "private-use part lowercases"


def rejects(value):
    try:
        normalize_locale_tag(value)
    except Exception:
        return True
    return False


assert rejects(42), "non-string is rejected"
assert rejects(""), "empty tag is rejected"
assert rejects("en--US"), "empty subtag is rejected"
assert rejects("e"), "one-letter language is rejected"
assert rejects("en-Lat"), "three-letter second subtag fits no slot"
assert rejects("en-US-Latn"), "script after region is rejected"
assert rejects("en-Latn-GB-boont-extra"), "five core subtags are rejected"
assert rejects("en-x"), "bare x marker is rejected"
assert rejects("en-x-waytoolong9"), "overlong private-use subtag"
print("ok")
