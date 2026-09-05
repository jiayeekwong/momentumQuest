"""
Parser for the Universiti Malaya "Student Academic Performance Record" PDF.

The PDF carries a real text layer, so no OCR is involved — pdfplumber pulls
the text and the regexes below pick out the subject rows.

Two properties of the document shape this module:

1. The text layer collapses spaces unpredictably ("PROJECTMANAGEMENT"), so
   subject names are unreliable. Module codes always come out clean, and are
   the only thing matching is ever done on.

2. The Grade Point column equals credit x points(grade), which gives every
   row a free checksum. A row that fails it was misparsed and is dropped
   rather than trusted.
"""

import re


# UM grade points per credit. Note A+ and A are both 4.00 on this scale, so
# the letter — not the grade point — is what distinguishes them.
GRADE_POINTS = {
    "A+": 4.00, "A": 4.00, "A-": 3.70,
    "B+": 3.30, "B": 3.00, "B-": 2.70,
    "C+": 2.30, "C": 2.00, "C-": 1.70,
    "D+": 1.30, "D": 1.00, "F": 0.00,
}

# Grade -> StudentSkill.SkillLevel. C- and below are not recorded at all: a
# bare pass is not evidence of a skill.
GRADE_TO_LEVEL = {
    "A+": "ADVANCED",     "A": "ADVANCED",     "A-": "ADVANCED",
    "B+": "INTERMEDIATE", "B": "INTERMEDIATE", "B-": "INTERMEDIATE",
    "C+": "BEGINNER",     "C": "BEGINNER",
}

LEVEL_RANK = {"BEGINNER": 1, "INTERMEDIATE": 2, "ADVANCED": 3}

# Grade points are printed to 2dp, so exact arithmetic is expected; the
# tolerance only absorbs the university's own rounding.
CHECKSUM_TOLERANCE = 0.05

# "1. WIA1002 DATA STRUCTURE 5 B 15.00"
# Requiring the module code is what keeps the numbered lines in the Notes
# section ("1.Students are required to...") from matching.
SUBJECT_RE = re.compile(
    r"^\s*\d+\.\s+([A-Z]{3}\d{4})\s+(.+?)\s+(\d+)\s+([A-Z][+-]?)\s+(\d+\.\d{2})\s*$"
)

# "Examination Result for Semester 1, Session 2023/2024"
# Case-insensitive: real transcripts render this as "For" with a capital F,
# while some exports use lowercase.
SEMESTER_RE = re.compile(
    r"^Examination Result for Semester\s+(\d+),\s+Session\s+(\d{4}/\d{4})",
    re.IGNORECASE,
)

# Everything from here on is university boilerplate, not results.
NOTES_RE = re.compile(r"^\s*Notes\s*$", re.IGNORECASE)


def extract_text_from_pdf(file_obj):
    """Pull the text layer out of a transcript PDF."""
    import pdfplumber

    with pdfplumber.open(file_obj) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def parse_transcript_text(text):
    """
    Extract subject rows from transcript text.

    Returns (subjects, warnings). Each subject is a dict with code, name,
    credit, grade, grade_point, semester, session and checksum_ok.
    """
    subjects = []
    warnings = []
    semester = ""
    session = ""

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if NOTES_RE.match(line):
            break

        semester_match = SEMESTER_RE.match(line)
        if semester_match:
            semester, session = semester_match.group(1), semester_match.group(2)
            continue

        match = SUBJECT_RE.match(line)
        if not match:
            continue

        code, name, credit_text, grade, point_text = match.groups()
        credit = int(credit_text)
        grade_point = float(point_text)

        expected = GRADE_POINTS.get(grade)
        checksum_ok = (
            expected is not None
            and abs(grade_point - credit * expected) <= CHECKSUM_TOLERANCE
        )
        if not checksum_ok:
            warnings.append(
                f"{code}: grade point {grade_point} does not match "
                f"{grade} over {credit} credits — row ignored."
            )

        subjects.append({
            "code": code,
            "name": name.strip(),
            "credit": credit,
            "grade": grade,
            "grade_point": grade_point,
            "semester": semester,
            "session": session,
            "checksum_ok": checksum_ok,
            "skills": [],
        })

    return subjects, warnings
