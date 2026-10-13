"""A JS/TS rename follows the module's own namespace, and no other receiver.

``import * as ns from "./a"`` makes ``ns.fetchPage`` the definition in ``a``,
and nothing else spelled ``.fetchPage`` is: ``other.fetchPage()`` reaches
whatever ``other`` holds, and ``{ fetchPage: 1 }`` is a key. The index records
both member calls as references named ``fetchPage``, which is why a rename that
trusted it rewrote all of them.
"""

from __future__ import annotations

from pathlib import Path

from mcgyvr.rename import apply as rename_apply
from tests.renaming import committed, read

A = "export function fetchPage(url) {\n  return url;\n}\n"

USE = """\
import * as ns from "./a";

export function go(other) {
  ns.fetchPage(1);
  other.fetchPage(2);
  return { fetchPage: 1 };
}
"""

TREE = {"src/a.js": A, "src/use.js": USE}


def test_a_namespace_member_is_renamed_and_another_receiver_is_not(
    tmp_path: Path,
) -> None:
    repo = committed(tmp_path / "repo", TREE)

    report = rename_apply(repo, "fetchPage", "getPage")

    after = read(repo, TREE)
    assert after["src/a.js"] == A.replace("fetchPage", "getPage")
    assert after["src/use.js"] == USE.replace("ns.fetchPage", "ns.getPage")
    assert "src/use.js:5 other.fetchPage" in report.left_alone
    assert "src/use.js:6 fetchPage (an object key)" in report.left_alone


def test_a_barrel_that_re_exports_carries_the_rename_to_its_importers(
    tmp_path: Path,
) -> None:
    tree = {
        "src/lib/a.ts": "export const fetchPage = (url: string) => url;\n",
        "src/lib/index.ts": 'export { fetchPage } from "./a";\n',
        "src/main.ts": (
            'import { fetchPage } from "./lib";\n'
            "function local(fetchPage: number) {\n  return fetchPage;\n}\n"
            "fetchPage(String(local(1)));\n"
        ),
    }
    repo = committed(tmp_path / "repo", tree)

    rename_apply(repo, "fetchPage", "getPage")

    after = read(repo, tree)
    assert after["src/lib/a.ts"] == "export const getPage = (url: string) => url;\n"
    assert after["src/lib/index.ts"] == 'export { getPage } from "./a";\n'
    assert after["src/main.ts"] == (
        'import { getPage } from "./lib";\n'
        "function local(fetchPage: number) {\n  return fetchPage;\n}\n"
        "getPage(String(local(1)));\n"
    )


def test_an_import_from_a_package_of_the_same_name_is_left_alone(
    tmp_path: Path,
) -> None:
    tree = {
        "src/a.js": A,
        "src/other.js": 'import { fetchPage } from "some-package";\nfetchPage(1);\n',
    }
    repo = committed(tmp_path / "repo", tree)

    report = rename_apply(repo, "fetchPage", "getPage")

    assert read(repo, tree)["src/other.js"] == tree["src/other.js"]
    assert report.files == ("src/a.js",)
