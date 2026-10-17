""

from importlib.metadata import PackageNotFoundError, version

try:
    #
    #om
    #
    #
    __version__ = version("mcgyvr")
except PackageNotFoundError:
    # a
    #
    __version__ = "0.0.0+uninstalled"
