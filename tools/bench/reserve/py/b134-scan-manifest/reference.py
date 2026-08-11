"""Compare a digest manifest against held file contents and report the drift."""


def scan_manifest(manifest, files):
    def digest_of(text):
        h = 0
        for ch in text:
            h = (h * 31 + ord(ch)) % 65521
        return format(h, "04x")

    if not isinstance(manifest, str):
        raise ValueError("the manifest must be a string")
    for name, content in files.items():
        if not isinstance(content, str):
            raise ValueError(f"held content is not a string: {name}")
    expected = {}
    for line in manifest.split("\n"):
        if line.strip() == "":
            continue
        cut = line.find(" ")
        if cut < 0:
            raise ValueError(f"manifest line has no space: {line}")
        digest = line[:cut]
        name = line[cut + 1:]
        if len(digest) != 4 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"malformed digest: {digest}")
        if name == "":
            raise ValueError("manifest line names no file")
        if name in expected:
            raise ValueError(f"file listed twice: {name}")
        expected[name] = digest
    intact = []
    altered = []
    lost = []
    strays = []
    for name, digest in expected.items():
        if name not in files:
            lost.append(name)
        elif digest_of(files[name]) == digest:
            intact.append(name)
        else:
            altered.append(name)
    for name in files:
        if name not in expected:
            strays.append(name)
    return {
        "intact": sorted(intact),
        "altered": sorted(altered),
        "lost": sorted(lost),
        "strays": sorted(strays),
    }
