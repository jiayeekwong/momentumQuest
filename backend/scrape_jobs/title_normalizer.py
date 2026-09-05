"""Turning a raw employer job title into a Normalized Job Title.

Three values are kept apart throughout the system and this module produces the
middle one:

    Raw Job Title          "Senior Front-End Engineer (Remote)"
    Normalized Job Title   "frontend engineer"
    Market Role            "Frontend Developer"

The Normalized Job Title is *matching evidence* -- a formatting-only reduction
of what the employer wrote. It is never shown to a student as a career option
and never stands in for a Market Role.

Normalization removes only things that cannot change what the job is:
capitalisation, punctuation, hyphenation, whitespace, remote/WFH markers,
location and salary suffixes, and recruitment marketing. It never removes a
word that carries occupational meaning.
"""

import re
import unicodedata


# --- Career level ----------------------------------------------------------
#
# Only genuine levels live here. Manager, Head, Lead, Principal, Architect,
# Administrator, Consultant, Specialist, Support, Officer, Engineer, Analyst,
# Developer and Scientist are deliberately absent: each of them names what the
# job *is*, not how senior it is. Treating them as levels is what previously
# turned "IT Manager / Assistant Manager" into "IT Assistant" and matched it to
# a support role -- a title-destroying bug that CareerLevelTests guards against.
#
# Order is precedence: the first level found is the one reported, so a title
# advertising a range ("IT System Engineer (Senior/Junior)") is recorded at its
# entry point, which is the level a student browsing careers is looking for.
CAREER_LEVEL_PATTERNS = (
    ("INTERN",    (r"\bintern(?:ship)?\b", r"\btrainee\b", r"\bapprentice\b")),
    ("GRADUATE",  (r"\bfresh\s+grad(?:uate)?s?\b", r"\bgraduate\b")),
    ("JUNIOR",    (r"\bjunior\b", r"\bjnr\b", r"\bjr\.?\b",
                   r"\bentry[ -]?level\b", r"\bfresh\s+entry\b")),
    ("ASSOCIATE", (r"\bassociate\b",)),
    ("MID",       (r"\bmid[ -]?level\b", r"\bmid\b")),
    ("SENIOR",    (r"\bsenior\b", r"\bsnr\b", r"\bsr\.?\b")),
)

#: Removing "associate" can destroy a title -- "Associate Engineer" becomes
#: "engineer", which names no career. It is only stripped when enough of the
#: title survives to still describe a function.
ASSOCIATE_MINIMUM_REMAINING_WORDS = 2

# Bracketed asides in a posting are recruiter copy, never part of the role:
# "Software Engineer (ERP)", "Data Center Engineer (Fresh Grad Welcomed)".
PARENTHETICAL_PATTERN = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")

#: Marketing, logistics and pay copy that survives outside brackets. Every
#: entry here is metadata about the advert, not about the occupation.
NOISE_PATTERNS = (
    r"fresh\s+grad(?:uate)?s?\s+welcomed?",
    r"urgent(?:ly)?\s+hiring",
    r"immediate\s+hiring",
    r"hiring\s+now",
    r"walk\s*-?\s*in\s+interview",
    r"work\s+from\s+home",
    r"\bremote\b",
    r"\bonsite\b",
    r"\bon[ -]site\b",
    r"\bhybrid\b",
    r"\bwfh\b",
    r"\bl[1-3]\s*/?\s*l[1-3]\b",
    r"\bintake\b.*$",
    r"\bsalary\b.*$",
    # Pay: "| RM4,000 - RM5,000", "RM 3k-5k", "(up to RM8000)".
    r"\brm\s*[\d,.]+\s*k?\b.*$",
    r"\bup\s+to\s+rm\b.*$",
    # Placement: "based in Penang", "Singapore-based", "- Penang & KL".
    r"\bbased\s+(?:in|at)\b.*$",
    r"\b(?:kuala\s+lumpur|klang\s+valley|kl|selangor|penang|johor|melaka|"
    r"ipoh|cyberjaya|puchong|petaling\s+jaya|pj|sarawak|sabah|malaysia|"
    r"singapore)[\s-]+based\b",
    # A trailing list of offices: "Software Engineer - Penang & KL".
    r"[-–,|]\s*(?:kuala\s+lumpur|klang\s+valley|kl|selangor|penang|johor|"
    r"melaka|ipoh|cyberjaya|puchong|petaling\s+jaya|pj|sarawak|sabah|"
    r"malaysia|singapore)\b[\s&/and]*"
    r"(?:kuala\s+lumpur|kl|selangor|penang|johor|melaka|ipoh|cyberjaya|"
    r"puchong|pj|singapore)?\s*$",
    # Regional scope: an advert covering APAC is still the same job.
    r"\bapac\b", r"\bemea\b", r"\banz\b",
    r"\basia[\s-]?pacific\b", r"\bsouth[\s-]?east\s+asia\b",
    # Employment terms: "12 Months Contract", "Contract Basis", "Part Time".
    r"\b\d+\s*(?:months?|years?)\s*contract\b",
    r"\bcontract\s+basis\b",
    r"\bpart[ -]time\b",
    r"\bfull[ -]time\b",
    r"\bpermanent\s+position\b",
    # Language and nationality requirements.
    r"\b(?:preferr?able\s+)?mandarin\s+speak(?:er|ing)\b",
    r"\b(?:japanese|korean|cantonese|chinese)\s+speak(?:er|ing)\b",
    r"\bmalaysians?\s+only\b",
    r"\btraining\s+provided\b",
)
NOISE_PATTERN = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)

# Employers post the short form ("IT Executive") where a role vocabulary spells
# it out ("Information Technology Executive"). Expanding the employer side is
# what lets two spellings of one title group together.
ABBREVIATION_EXPANSIONS = (
    (r"\bict\b", "information technology"),
    (r"\bi\.?t\.?\b(?!\w)", "information technology"),
    (r"\bai\b", "artificial intelligence"),
    (r"\bml\b", "machine learning"),
    (r"\bqa\b", "quality assurance"),
    (r"\bqc\b", "quality control"),
    (r"\bsqa\b", "software quality assurance"),
    (r"\bdba\b", "database administrator"),
    (r"\bbi\b", "business intelligence"),
    (r"\bui\b", "user interface"),
    (r"\bux\b", "user experience"),
    (r"\bsw\b", "software"),
    (r"\bhw\b", "hardware"),
    (r"\bsys\b", "system"),
    (r"\badmin\b", "administrator"),
    (r"\bdev\b", "developer"),
    (r"\bdevs\b", "developer"),
    (r"\beng\b", "engineer"),
    (r"\bexec\b", "executive"),
    (r"\bmgr\b", "manager"),
    (r"\bsre\b", "site reliability engineer"),
    (r"\bnoc\b", "network operations centre"),
    (r"\bpm\b", "project manager"),
    # Spelling variants that are the same word.
    (r"\bfront[\s-]?end\b", "frontend"),
    (r"\bback[\s-]?end\b", "backend"),
    (r"\bfull[\s-]?stack\b", "full stack"),
    (r"\bfullstack\b", "full stack"),
    (r"\bweb[\s-]?site\b", "website"),
    (r"\bhelp[\s-]?desk\b", "helpdesk"),
    (r"\bcyber[\s-]?security\b", "cybersecurity"),
    (r"\bdata[\s-]?cent(?:er|re)\b", "data centre"),
    (r"\bdev[\s-]?ops\b", "devops"),
)

# Employers cram several roles into one posting: "Web Developer / Full Stack
# Developer". Deliberately excludes "and", which joins qualifiers more often
# than it joins roles ("Research and Development Engineer").
SEGMENT_SPLITTER = re.compile(r"\s*(?:[|/·•]|\s-\s|\bcum\b|,)\s*", re.IGNORECASE)

MINIMUM_SEGMENT_LENGTH = 4


def strip_recruiter_noise(title):
    """Remove bracketed asides and advert metadata from a raw title."""
    value = PARENTHETICAL_PATTERN.sub(" ", title or "")
    value = NOISE_PATTERN.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip(" -,/|")


def expand_abbreviations(title):
    """Rewrite common employer abbreviations into their full wording."""
    value = title or ""
    for pattern, replacement in ABBREVIATION_EXPANSIONS:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip()


def title_segments(title):
    """Split a multi-role title into its individually matchable parts."""
    return [
        segment.strip()
        for segment in SEGMENT_SPLITTER.split(title or "")
        if len(segment.strip()) >= MINIMUM_SEGMENT_LENGTH
    ]


def normalize_occupation_label(value):
    """Casefold and flatten punctuation, keeping every meaningful word."""
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[/_,()\[\]{}]+", " ", value)
    value = re.sub(r"[^\w+#. -]", " ", value)
    value = re.sub(r"[-\s]+", " ", value)
    return value.strip(" .")


def normalize_title(title):
    """A Raw Job Title reduced to its Normalized Job Title.

    The whole pipeline, in order, because the order is what makes it work:

      1. strip recruiter noise   "(Remote)", "urgent hiring", "| RM4,000"
      2. expand abbreviations    "QA" -> "quality assurance", "Front-End" -> "frontend"
      3. normalize the label     casefold, punctuation, whitespace

    Career level is *not* removed here -- "senior software engineer" is a
    faithful normalization of what the employer wrote. Removing the level is a
    separate, explicitly reversible step so the two can be reported apart.
    """
    return normalize_occupation_label(
        expand_abbreviations(strip_recruiter_noise(title))
    )


def extract_career_level(title):
    """The career level the title states, or "" when it states none.

    Read before recruiter noise is stripped, because "Fresh Grad Welcomed" is
    marketing for the advert *and* the only statement of level it carries.
    """
    text = normalize_occupation_label(expand_abbreviations(title))
    for level, patterns in CAREER_LEVEL_PATTERNS:
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
            return level
    return ""


def title_without_career_level(title, strip_associate=False):
    """The Normalized Job Title with genuine career levels removed.

    "Senior Data Engineer", "Junior Data Engineer" and "Data Engineer" all
    reduce to "data engineer" -- the same occupational function at three
    levels. Words that name a function are never touched, so "IT Manager"
    stays "information technology manager".

    ``strip_associate`` is off by default. "Associate" sometimes marks a level
    ("Associate Software Engineer") and sometimes is the job ("Associate,
    Client Services"), so it is only removed on an explicit second pass and
    only when enough of the title survives to still describe a function.
    """
    value = normalize_title(title)
    for level, patterns in CAREER_LEVEL_PATTERNS:
        if level == "ASSOCIATE":
            continue
        for pattern in patterns:
            value = re.sub(pattern, " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip()

    if strip_associate:
        candidate = re.sub(r"\s+", " ",
                           re.sub(r"\bassociate\b", " ", value,
                                  flags=re.IGNORECASE)).strip()
        if len(candidate.split()) >= ASSOCIATE_MINIMUM_REMAINING_WORDS:
            return candidate
    return value
