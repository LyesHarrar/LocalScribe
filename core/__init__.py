"""
LocalScribe — Package Core.
"""

from core.hardware_profiler import configure_cuda_paths
configure_cuda_paths()

from core.version import (
    __version__,
    __author__,
    __github_repo__,
    __github_author__,
    __releases_url__,
    check_for_updates,
)

__all__ = [
    "__version__",
    "__author__",
    "__github_repo__",
    "__github_author__",
    "__releases_url__",
    "check_for_updates",
]
