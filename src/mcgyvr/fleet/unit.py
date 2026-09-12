"""A unit is named by its whole resolved launch.

``unt-`` hashes everything that decides what the process is: the engine, the
resolved image id, the weights' sha256, the argv, the environment and the
card's compute capability. There is no hand-kept field list: any flag whose
effect differs per model family has to move the name, so the launch is hashed
whole. A tag is not an identity — a rebuild replaces it under the same string,
so the hashed value is the image's ``sha256:`` Id.
"""

from __future__ import annotations

from typing import Any

from mcgyvr.fleet import ids

REQUIRED_FIELDS = ("engine", "image_id", "weights_sha256", "argv", "env", "gpu_cc")


def unit_id(launch: dict[str, Any]) -> str:
    """``unt-`` plus a digest of the launch's resolved fields."""
    for field in REQUIRED_FIELDS:
        if field not in launch:
            raise ValueError(
                f"launch is missing {field!r}; a unit is named by its whole "
                "resolved launch"
            )
    image_id = launch["image_id"]
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        raise ValueError(
            f"image is {image_id!r}; a unit is named by its image's sha256 id, "
            "not a tag"
        )
    return ids.digest("unt-", launch)
