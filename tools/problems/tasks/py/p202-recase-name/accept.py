from solution import recase_name

assert recase_name("parseURL", "snake") == "parse_url", "trailing acronym goes small"
assert recase_name("XMLHTTPRequest", "kebab") == "xmlhttp-request", "run hands over its last capital"
assert recase_name("utf8Frame", "snake") == "utf_8_frame", "a digit run is its own word"
assert recase_name("base64Value", "shout") == "BASE_64_VALUE", "shout uppercases every word"
assert recase_name("http-probe-id", "pascal") == "HttpProbeId", "hyphens are word ends"
assert recase_name("parse_url", "camel") == "parseUrl", "small words stay small in camel"
assert recase_name("parseURL", "camel") == "parseURL", "an acronym keeps its capitals in camel"
assert recase_name("parseURL", "pascal") == "ParseURL", "an acronym keeps its capitals in pascal"
assert recase_name("HTTP", "camel") == "http", "the opening word is wholly small in camel"
assert recase_name("HTTP", "pascal") == "HTTP", "a lone acronym survives pascal"
assert recase_name("id", "kebab") == "id", "one word needs no joiner"
assert recase_name("ABc", "snake") == "a_bc", "a two capital run splits before a small letter"
assert recase_name("readXML2Frame", "kebab") == "read-xml-2-frame", "digits break an acronym"
assert [
    recase_name("PDF_reportV2", style)
    for style in ("snake", "kebab", "shout", "pascal", "camel")
] == [
    "pdf_report_v_2",
    "pdf-report-v-2",
    "PDF_REPORT_V_2",
    "PDFReportV2",
    "pdfReportV2",
], "every style reads the same cut"


def rejects(label, style):
    try:
        recase_name(label, style)
    except ValueError:
        return True
    return False


assert rejects("", "snake"), "an empty label is rejected"
assert rejects("_lead", "snake"), "a leading separator is rejected"
assert rejects("trail-", "snake"), "a trailing separator is rejected"
assert rejects("two__gaps", "snake"), "a doubled separator is rejected"
assert rejects("dot.name", "snake"), "a stray character is rejected"
assert rejects("fine", "title"), "an unknown style is rejected"
assert rejects(42, "snake"), "a non-string label is rejected"
assert rejects("fine", None), "a non-string style is rejected"
print("ok")
