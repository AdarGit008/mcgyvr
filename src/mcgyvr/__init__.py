"""mcgyvr — offload scoped coding work to a configurable worker ladder."""

from importlib.metadata import PackageNotFoundError, version

try:
    #: The version of the product that is installed, as the wheel's metadata
    #: says it — which is the tag it was built from (hatch-vcs). Read from
    #: the metadata and never spelled here, so the code cannot claim a
    #: version other than the one it was installed as.
    __version__ = version("mcgyvr")
except PackageNotFoundError:
    # The package is imported from a tree that was never installed — a
    # fixture, a bare checkout on sys.path. Not a version, and said so.
    __version__ = "0.0.0+uninstalled"
