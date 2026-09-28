"""kutu-doctor: live memory-health dashboard and control for kutu OS."""

from importlib import metadata

try:
    __version__ = metadata.version("kutu-doctor")
except metadata.PackageNotFoundError:
    __version__ = "0.1.0"
