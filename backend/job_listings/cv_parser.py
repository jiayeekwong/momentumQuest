"""Read a CV once, hand back what it says, and keep nothing.

The document itself is never stored. It is written to a private temporary
file only because pdfplumber needs a path, parsed, and deleted in a finally
block. What survives is the structured information the student confirms,
which is theirs to correct before it is saved anywhere.

The finally block covers an exception, including one raised inside pdfplumber.
It does **not** cover a hard kill -- SIGKILL, a container eviction, a power
loss -- because no in-process cleanup can. A CV left behind that way would sit
in the system temp directory indefinitely, so ``sweep_orphaned_cv_files`` runs
at the start of each parse and removes any older than SWEEP_AGE_SECONDS. That
makes the guarantee "a CV does not survive long after the request" rather than
the stronger claim this file used to make.

That ordering is the point. A stored CV is a standing liability: it carries a
phone number, an address, referees and often a photograph, it has to be
served back to companies through some authenticated path, and it must be
deleted on request. Extracting the few fields the system actually uses avoids
all of it.

Phase 1 reads PDFs only. A .doc/.docx parser needs a dependency this project
does not have, and a Word file's ZIP signature would be indistinguishable
from any other archive at validation time. A student uploading one is told to
export a PDF rather than being silently mis-parsed.
"""

import logging
import os
import re
import tempfile
import time

# Module level, not inside parse_cv: transcript_parser imports only `re` at
# module scope (pdfplumber is loaded lazily inside the function), and
# job_listings already depends on resources through its serializers, so there
# is no cycle to avoid here.
from resources.transcript_parser import extract_text_from_pdf

logger = logging.getLogger(__name__)

# Headings a CV uses to introduce each section. Matched on their own line so
# the word "education" inside a sentence does not open a section.
SECTION_PATTERNS = {
    "education": (
        r"education", r"academic\s+(?:background|qualification)s?",
        r"qualifications?",
    ),
    "experience": (
        r"(?:work\s+)?experience", r"employment(?:\s+history)?",
        r"professional\s+experience", r"internships?",
    ),
    "skills": (r"(?:technical\s+)?skills?", r"competenc(?:y|ies)", r"expertise"),
}

# Everything that ends a section without opening one we care about.
OTHER_HEADINGS = (
    r"projects?", r"certifications?", r"awards?", r"references?", r"referees?",
    r"activities", r"interests?", r"languages?", r"publications?", r"summary",
    r"objective", r"profile", r"contact",
)

MAX_SECTION_LINES = 40
MAX_ENTRY_LENGTH = 200


def _heading_key(line):
    """Which section this line opens, '' for a heading we skip, None otherwise."""
    stripped = line.strip().strip(":").strip()
    # A heading is short. "Experience working with Django" is not one.
    if not stripped or len(stripped) > 40:
        return None
    lowered = stripped.lower()
    for key, patterns in SECTION_PATTERNS.items():
        if any(re.fullmatch(pattern, lowered) for pattern in patterns):
            return key
    if any(re.fullmatch(pattern, lowered) for pattern in OTHER_HEADINGS):
        return ""
    return None


def split_sections(text):
    """Group a CV's lines under the heading that introduced them."""
    sections = {key: [] for key in SECTION_PATTERNS}
    current = None
    for raw_line in (text or "").splitlines():
        key = _heading_key(raw_line)
        if key is not None:
            current = key or None
            continue
        line = raw_line.strip()
        if current and line and len(sections[current]) < MAX_SECTION_LINES:
            sections[current].append(line[:MAX_ENTRY_LENGTH])
    return sections


def extract_skills(text):
    """Skills from the whole document, mapped onto the standardized table.

    Reuses the scraper's extractor, so a CV and a job advert are read with one
    vocabulary and one set of aliases -- which is what makes the match score
    comparable at all. Free-text skills are never invented: a word that is not
    in the Skill table is not a skill the system can reason about.
    """
    from scrape_jobs.skill_extractor import extract_skills_from_text

    return extract_skills_from_text(text or "")


# How old an abandoned temporary CV must be before the sweeper takes it.
# Comfortably longer than any parse, so a concurrent request's file is never
# deleted out from under it.
SWEEP_AGE_SECONDS = 15 * 60

TEMP_PREFIX = "cv-"


def sweep_orphaned_cv_files(now=None):
    """Delete temporary CVs a previous process failed to clean up.

    A ``finally`` block cannot run if the process is killed outright, so
    without this a hard termination mid-parse would leave an identity-bearing
    PDF in the system temp directory for good.

    Called at the start of each parse rather than from a scheduler: it is the
    same code path that creates these files, it costs one directory listing,
    and it needs no cron entry that someone has to remember to install.

    Never raises -- a sweep failing must not stop a student applying for a job.
    """
    cutoff = (now or time.time()) - SWEEP_AGE_SECONDS
    directory = tempfile.gettempdir()
    removed = 0

    try:
        names = os.listdir(directory)
    except OSError:
        logger.warning("Could not list the temporary directory to sweep CVs")
        return 0

    for name in names:
        if not (name.startswith(TEMP_PREFIX) and name.endswith(".pdf")):
            continue
        path = os.path.join(directory, name)
        try:
            if os.path.getmtime(path) > cutoff:
                continue
            os.unlink(path)
            removed += 1
        except FileNotFoundError:
            # Another worker got there first, which is the wanted outcome.
            continue
        except OSError:
            logger.warning("Could not remove an abandoned temporary CV")

    if removed:
        logger.info("Swept %s abandoned temporary CV file(s)", removed)
    return removed


def parse_cv(upload):
    """Extract structured information from an uploaded CV. Stores nothing.

    Returns a dict of skills / education / experience. The temporary file is
    removed in a finally block, so no path exists after this returns even if
    parsing raised. A file abandoned by an earlier hard kill is removed by the
    sweep below rather than left forever.
    """
    sweep_orphaned_cv_files()

    handle, temporary_path = tempfile.mkstemp(suffix=".pdf", prefix=TEMP_PREFIX)
    try:
        with os.fdopen(handle, "wb") as destination:
            for chunk in upload.chunks():
                destination.write(chunk)

        text = extract_text_from_pdf(temporary_path)
    finally:
        # Deleted whether parsing succeeded or raised. A hard kill bypasses
        # this, which is what the sweeper above is for.
        try:
            os.unlink(temporary_path)
        except OSError:
            logger.warning("Could not delete temporary CV at %s", temporary_path)

    if not text or not text.strip():
        return {
            "readable": False,
            "skills": [],
            "education": [],
            "experience": [],
            "detail": (
                "This PDF contains no readable text, so it is most likely a "
                "scan or an image. Please upload a CV exported as a text PDF."
            ),
        }

    sections = split_sections(text)
    skills = extract_skills(text)

    return {
        "readable": True,
        "skills": [
            {"skill_id": skill.id, "skill_name": skill.skill_name,
             "skill_category": skill.skill_category}
            for skill in skills
        ],
        "education": sections["education"],
        "experience": sections["experience"],
        "detail": (
            "We read your CV and did not keep the file. Check what we found "
            "below, correct anything wrong, and it will be attached to your "
            "application."
        ),
    }
