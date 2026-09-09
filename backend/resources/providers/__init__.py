"""Course providers, all feeding one catalogue and one skill extractor.

Importing this package registers every adapter, so ``get_provider("Microsoft
Learn")`` works without the caller knowing which module defines it.
"""

from .authority import (  # noqa: F401
    authority_index, is_authoritative, preference_rank, rank_resources,
)
from .base import CourseProvider, get_provider, provider_names, register  # noqa: F401
from .dedup import deduplicate, cross_provider_report  # noqa: F401
from .normalize import InvalidCourse, merge_course, normalize_course  # noqa: F401
from .runner import (  # noqa: F401
    AcquisitionInterrupted, acquire, checkpoint_for,
)
from . import microsoft_learn  # noqa: F401  (registers the adapter)
from . import edx  # noqa: F401  (registers the adapter)
