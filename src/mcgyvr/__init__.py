"""Package root for mcgyvr.

The only public attribute defined here is ``__version__``, resolved from the
metadata of the installed ``mcgyvr`` distribution when that metadata exists.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    #: Ask the installed distribution metadata for the version of "mcgyvr".
    #: The value comes from the package metadata written at install time, so it
    #: describes which build of the package is actually importable.
    #: When the distribution is not installed, importlib.metadata raises below.
    __version__ = version("mcgyvr")
except PackageNotFoundError:
    # Distribution metadata is unavailable, e.g. when running from a source
    # checkout rather than an installed distribution.
    __version__ = "0.0.0+uninstalled"
