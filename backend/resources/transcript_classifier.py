"""Decide whether an uploaded PDF is plausibly an academic transcript.

Answers a different question from the parser. The parser asks "can I read
examination rows out of this text"; this asks "is this document what it
claims to be, and does it belong to the person who uploaded it". A file can
pass the first and fail the second: the layout is public, and anyone can
typeset a page that parses perfectly.

**Scoring deliberately ignores anything cosmetic.** A logo, a filename, or
the word "transcript" in a heading are trivially forged and score nothing on
their own. Weight sits on things a forger has to get arithmetically right or
already know about the uploading student:

  * the matric number matching the *logged-in* student (25) -- the single
    strongest signal, because it cannot be lifted from a sample document
  * grade-point arithmetic checking out across most rows (10)
  * enough real module rows to be a record rather than a mock-up (10)

Phase 1 covers the Universiti Malaya text-layer format only. No OCR, so a
scanned transcript yields no text and is reported as unreadable rather than
guessed at. Other institutions and scanned documents come later, behind
per-institution parser profiles.

Passing here still does not mean authentic. It means "worth an
administrator's time"; issuer verification is a separate state.
"""

import re
from dataclasses import dataclass, field

# Institutions whose transcript format Phase 1 can actually read. Matching is
# on the institution name in the document text, not on a filename or logo.
RECOGNISED_INSTITUTIONS = (
    ("Universiti Malaya", (
        r"universiti\s+malaya",
        r"university\s+of\s+malaya",
    )),
)

# The document must call itself a results record somewhere. Worth points, but
# never sufficient -- this is the easiest signal in the list to fake.
TITLE_PATTERNS = (
    r"student\s+academic\s+performance\s+record",
    r"academic\s+transcript",
    r"examination\s+result",
)

# "WIA1002" style module codes are the university's own vocabulary.
MATRIC_PATTERNS = (
    # UM matric numbers: a letter-digit pattern such as "17204532/1" or
    # "S2012345". Kept broad because the exact shape varies by intake year.
    r"\b([A-Z]{1,3}\s?\d{6,9}(?:/\d)?)\b",
    r"\b(\d{8}(?:/\d)?)\b",
)

SEMESTER_PATTERN = r"semester\s+\d+.{0,20}session\s+\d{4}/\d{4}"

SCORE_INSTITUTION = 20
SCORE_TITLE = 15
SCORE_MATRIC_MATCH = 25
SCORE_NAME_MATCH = 10
SCORE_SEMESTER = 10
SCORE_MODULE_ROWS = 10
SCORE_CHECKSUM = 10

LIKELY_THRESHOLD = 80
UNCERTAIN_THRESHOLD = 50

MIN_MODULE_ROWS = 2
# Share of parsed rows whose grade-point arithmetic must hold.
MIN_CHECKSUM_RATIO = 0.8


@dataclass
class TranscriptClassification:
    document_type: str
    score: int
    institution: str
    identity_matched: bool | None
    #: Whether the document reads as a transcript *setting identity aside*.
    #:
    #: ``document_type`` cannot answer this: a transcript belonging to someone
    #: else is forced to NOT_TRANSCRIPT, which is the right call for whether
    #: to accept it and the wrong one for what to tell the student. Refusing a
    #: holiday booking with "the identity on this document does not match your
    #: account" accuses them of using another person's results when they
    #: simply picked the wrong file.
    looks_like_transcript: bool = False
    reasons: list = field(default_factory=list)


def normalise(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def detect_institution(text):
    haystack = normalise(text)
    for name, patterns in RECOGNISED_INSTITUTIONS:
        if any(re.search(pattern, haystack) for pattern in patterns):
            return name
    return ""


def candidate_matrics(text):
    """Every matric-shaped token in the document."""
    found = set()
    for pattern in MATRIC_PATTERNS:
        for match in re.findall(pattern, text or "", re.IGNORECASE):
            found.add(re.sub(r"\s+", "", match).upper())
    return found


def matric_matches(text, student):
    """Whether the student's own matric number appears in the document.

    Returns None when the student has no matric number recorded, which is
    "could not check" and must not be reported as a failed check.

    The comparison is in memory. Neither the document's identifiers nor the
    student's are written anywhere as a result of this call.
    """
    own = (getattr(student, "matric_number", "") or "").strip()
    if not own:
        return None
    normalised_own = re.sub(r"[^A-Z0-9/]", "", own.upper())
    if not normalised_own:
        return None

    candidates = candidate_matrics(text)
    if not candidates:
        # The document carries no matric-shaped token at all. That is "could
        # not check", not "checked and it belongs to somebody else" -- and the
        # difference decides whether a genuine transcript is refused outright.
        # UM's text layer collapses spacing unpredictably, so a real matric
        # number can fail to survive extraction.
        return None

    for candidate in candidates:
        stripped = re.sub(r"[^A-Z0-9/]", "", candidate)
        # Either direction: documents sometimes print the check digit suffix
        # and the profile sometimes omits it.
        if stripped == normalised_own:
            return True
        if stripped.split("/")[0] == normalised_own.split("/")[0]:
            return True

    # Matric-shaped tokens are present and none is the student's: a genuine
    # mismatch, and the only case that justifies refusing the upload.
    return False


def name_appears(text, student):
    """Whether the student's name appears, allowing for collapsed spacing.

    The UM text layer drops spaces unpredictably, so "SITI NURHALIZA" can come
    out as "SITINURHALIZA". Both forms are checked.
    """
    name = (getattr(student, "student_name", "") or "").strip()
    if len(name) < 4:
        return False
    haystack = normalise(text)
    squashed = re.sub(r"[^a-z0-9]", "", haystack)
    return name.lower() in haystack or re.sub(r"[^a-z0-9]", "", name.lower()) in squashed


def classify_transcript(text, student, subjects):
    """Score a document. See the module docstring for what the weights mean."""
    reasons = []
    score = 0

    institution = detect_institution(text)
    if institution:
        score += SCORE_INSTITUTION
        reasons.append(f"Recognised institution: {institution} (+{SCORE_INSTITUTION})")
    else:
        reasons.append("No recognised institution name found (+0)")

    haystack = normalise(text)
    if any(re.search(pattern, haystack) for pattern in TITLE_PATTERNS):
        score += SCORE_TITLE
        reasons.append(f"Document titles itself as a results record (+{SCORE_TITLE})")
    else:
        reasons.append("No academic-record title found (+0)")

    identity_matched = matric_matches(text, student)
    if identity_matched is True:
        score += SCORE_MATRIC_MATCH
        reasons.append(f"Matric number matches the uploading student (+{SCORE_MATRIC_MATCH})")
    elif identity_matched is False:
        reasons.append("Matric number does NOT match the uploading student (+0)")
    else:
        reasons.append("Student has no matric number on file, identity not checked (+0)")

    if name_appears(text, student):
        score += SCORE_NAME_MATCH
        reasons.append(f"Student name appears in the document (+{SCORE_NAME_MATCH})")
    else:
        reasons.append("Student name not found in the document (+0)")

    if re.search(SEMESTER_PATTERN, haystack):
        score += SCORE_SEMESTER
        reasons.append(f"Semester and academic session detected (+{SCORE_SEMESTER})")
    else:
        reasons.append("No semester/session line detected (+0)")

    rows = list(subjects or [])
    enough_rows = len(rows) >= MIN_MODULE_ROWS
    if enough_rows:
        score += SCORE_MODULE_ROWS
        reasons.append(f"{len(rows)} module rows parsed (+{SCORE_MODULE_ROWS})")
    else:
        reasons.append(f"Only {len(rows)} module row(s) parsed (+0)")

    checked = [row for row in rows if "checksum_ok" in row]
    passing = [row for row in checked if row.get("checksum_ok")]
    checksum_ratio = (len(passing) / len(checked)) if checked else 0.0
    checksum_ok = bool(checked) and checksum_ratio >= MIN_CHECKSUM_RATIO
    if checksum_ok:
        score += SCORE_CHECKSUM
        reasons.append(
            f"{len(passing)}/{len(checked)} rows pass grade-point arithmetic "
            f"(+{SCORE_CHECKSUM})")
    else:
        reasons.append(
            f"Only {len(passing)}/{len(checked) or 0} rows pass grade-point "
            "arithmetic (+0)")

    # Hard gates. A document may not be called a transcript on cosmetic
    # evidence alone, however high the arithmetic total climbs.
    mandatory = {
        "recognised institution": bool(institution),
        "identity match": identity_matched is True,
        f"at least {MIN_MODULE_ROWS} module rows": enough_rows,
        "grade-point arithmetic": checksum_ok,
    }
    unmet = [name for name, met in mandatory.items() if not met]

    if identity_matched is False:
        # Not uncertainty. The document carries a matric number and it belongs
        # to somebody else, so however well it scores on everything else it is
        # not this student's record. Queuing it as "uncertain" would invite a
        # reviewer to approve another person's results onto this profile.
        #
        # Distinct from identity_matched is None, which means the check could
        # not be made at all and is allowed to remain uncertain.
        document_type = "NOT_TRANSCRIPT"
        reasons.append(
            "Refused: the identity on this document does not match the "
            "uploading student.")
    elif score >= LIKELY_THRESHOLD and not unmet:
        document_type = "LIKELY_TRANSCRIPT"
    elif score >= UNCERTAIN_THRESHOLD:
        document_type = "UNCERTAIN"
        if unmet:
            reasons.append("Held back from LIKELY_TRANSCRIPT, missing: "
                           + ", ".join(unmet))
    else:
        document_type = "NOT_TRANSCRIPT"

    # A score high enough on its own but failing a gate must not be silently
    # downgraded without saying so.
    if score >= LIKELY_THRESHOLD and unmet:
        reasons.append(
            f"Score {score} would qualify, but these are mandatory and unmet: "
            + ", ".join(unmet))

    return TranscriptClassification(
        document_type=document_type,
        score=score,
        institution=institution,
        identity_matched=identity_matched,
        # Identity is excluded on purpose. It is one of the mandatory gates,
        # so counting it here would make this flag false whenever identity
        # fails -- which is precisely the case it exists to describe.
        looks_like_transcript=(
            score >= UNCERTAIN_THRESHOLD
            and not [name for name in unmet if name != "identity match"]),
        reasons=reasons,
    )
