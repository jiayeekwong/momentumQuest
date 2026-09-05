"""Locating files under PRIVATE_MEDIA_ROOT, portably and safely.

Two problems this solves.

**Separators.** ``os.path.join`` produces a backslash on Windows, so a path
stored there reads ``certificates\\cert_abc.pdf``. On Linux that is not a
directory and a filename -- it is one filename containing a backslash, so every
document uploaded on Windows would 404 after a deployment. Paths are therefore
written with forward slashes and read back tolerant of either, which keeps rows
already stored on Windows working.

**Containment.** Stored paths are generated from uuid4 and cannot currently
escape the private root, but the check is free and the consequence of being
wrong is serving or deleting an arbitrary file. It lived in three copies
before this module.
"""

import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)


def build_relative_path(directory, filename):
    """A new stored path, always with forward slashes."""
    return f"{directory}/{filename}"


def resolve(relative_path):
    """Absolute path for a stored file, or None if it escapes the private root.

    Accepts either separator so rows written on Windows still resolve.
    """
    if not relative_path:
        return None

    root = os.path.realpath(settings.PRIVATE_MEDIA_ROOT)

    # An already-resolved absolute path is accepted and re-checked rather than
    # mangled. Splitting one on "/" and rejoining it under the root produced a
    # nonsense path that failed containment, so a caller that passed the output
    # of this function back in got a silent refusal -- which is how an orphaned
    # certificate survived a failed upload.
    if os.path.isabs(relative_path):
        target = os.path.realpath(relative_path)
    else:
        parts = [part for part in relative_path.replace("\\", "/").split("/") if part]
        target = os.path.realpath(os.path.join(root, *parts))

    try:
        contained = os.path.commonpath([root, target]) == root
    except ValueError:
        # Different drives on Windows -- itself proof it is not inside the root.
        return None

    return target if contained else None


def stored_filename(relative_path):
    """The generated name a file is served under.

    Never the name the student uploaded: a file they saved as
    "040910101234_SPM.pdf" would otherwise put an identification number into a
    response header and into the reader's download folder.
    """
    return os.path.basename(relative_path.replace("\\", "/"))


def delete(relative_path):
    """Remove one stored file, if it is really inside the private root.

    Returns True when the file is gone afterwards (including when it was
    already absent), False when the path was refused or the unlink failed.

    Never raises. Every caller is cleaning up after something else -- a failed
    upload, a deleted account -- and a locked or missing file must not turn
    that into a 500. Failures are logged for follow-up instead.
    """
    target = resolve(relative_path)
    if target is None:
        if relative_path:
            logger.error("Refusing to delete a stored file outside PRIVATE_MEDIA_ROOT")
        return False

    try:
        os.remove(target)
    except FileNotFoundError:
        # Already gone: the outcome the caller wanted, either way.
        return True
    except OSError:
        logger.exception("Could not delete stored document %s", stored_filename(relative_path))
        return False
    return True
