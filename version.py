"""
Centralized version information for the Slug Flow Simulator.
Updated automatically by build_windows.py at build time.
"""

__app_name__ = "Slug Flow Simulator"
__version__ = "1.0.0"
__build_date__ = "2026-03-03"
__author__ = "Richard Belcher"


def version_tuple(v=None):
    """Convert version string '1.2.3' to tuple (1, 2, 3) for comparison."""
    return tuple(int(x) for x in (v or __version__).split("."))
