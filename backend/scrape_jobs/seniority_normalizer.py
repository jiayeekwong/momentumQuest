"""Separate a job title's rank from the role it names.

``Senior Software Engineer`` is not a different occupation from
``Software Engineer``; it is the same occupation at a different rank. Storing
the two as separate Market Roles splits one career's demand across two rows
and makes both look half as popular as they are.

So rank comes off the title before role matching, and is kept as metadata:

    Senior Software Engineer
        role_candidate   software engineer
        seniority_level  SENIOR

**The safety rule, which is the whole design.** A modifier is removed only if
what remains is *already* an approved Market Role or reviewed alias. Removal
can never invent a role.

    Chief Data Scientist  -> Data Scientist    (approved role: allowed)
    Chief Information Officer -> Information Officer
                                                (not approved: refused,
                                                 title kept intact)

Without that condition, stripping ``Chief`` would silently convert genuine
executive occupations into invented ones. The rule applies to every modifier
equally -- ``Chief`` is not special-cased, it is simply the one where the
failure is most obvious.

Nothing here does fuzzy matching. A title either reaches an approved name
exactly or it does not.
"""
import csv
import io
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "role_modifiers.csv"

#: Titles naming two roles at once. Splitting them and taking the first match
#: would assert a choice the advert did not make.
MULTI_ROLE = re.compile(r"\s(?:/|&|\bcum\b|\bor\b|\band\b)\s|/", re.I)

#: Recruitment and technology qualifiers. Not part of the role, and not
#: seniority either -- "(.NET/C#)" is a skill and "Open to Fresh Graduate" is
#: a hiring note.
QUALIFIER_BRACKET = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
QUALIFIER_TAIL = re.compile(
    r"\s*[-–—|]\s*(?:open to|fresh grad\w*|urgent\w*|hiring|"
    r"immediate\w*|walk[- ]?in|based in|remote|onsite|work from home|"
    r"rm ?[\d,]+|salary|up to|\d+\s*(?:month|year)).*$", re.I)

ENTRY_HINT = re.compile(r"\bfresh\s+grad\w*|\bgraduate\b|\bintern(?:ship)?\b|"
                        r"\bentry[- ]level\b|\btrainee\b", re.I)


def load_modifiers(path=DATA):
    """The reviewed modifier list. Never extended from advert text."""
    modifiers = {}
    if not path.exists():
        return modifiers
    with io.open(path, encoding="utf-8") as handle:
        rows = [line for line in handle if not line.lstrip().startswith("#")]
    for row in csv.DictReader(rows):
        key = (row.get("modifier") or "").strip().lower()
        if key:
            modifiers[key] = (row.get("seniority_level") or "").strip().upper()
    return modifiers


MODIFIERS = load_modifiers()


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().strip(" -,/|")


def split_qualifiers(raw_title):
    """Pull recruitment and technology qualifiers off a title.

    Returns (core_title, qualifiers). The qualifiers are returned rather than
    discarded: "(.NET/C#)" belongs to skills metadata, and throwing it away
    here would lose it for good.
    """
    # The brackets are punctuation; the content is what downstream skill
    # extraction wants, so they are stripped here rather than by every caller.
    qualifiers = [_clean(q).strip("()[]")
                  for q in QUALIFIER_BRACKET.findall(raw_title)]
    core = QUALIFIER_BRACKET.sub(" ", raw_title)

    tail = QUALIFIER_TAIL.search(core)
    if tail:
        qualifiers.append(_clean(tail.group(0)))
        core = core[:tail.start()]

    return _clean(core), [q for q in qualifiers if q]


def peel_modifiers(title):
    """Strip leading rank words, returning (remainder, removed, level).

    Only *leading* modifiers are considered. "Senior" in
    "Engineer, Senior Systems" is not a rank prefix and removing it would
    change what the title says.
    """
    remainder, removed, level = _clean(title), [], None
    while True:
        match = re.match(r"^([A-Za-z\.]+)\s+(.*)$", remainder)
        if not match:
            break
        head = match.group(1).lower().strip()
        if head not in MODIFIERS:
            break
        rest = _clean(match.group(2))
        if not rest:
            break                      # the modifier is the whole title
        removed.append(head)
        level = level or MODIFIERS[head]
        remainder = rest
    return remainder, removed, level


def analyse(raw_title, is_approved):
    """Split a raw title into role candidate, rank and qualifiers.

    ``is_approved(name)`` must return True when ``name`` is already an
    approved Market Role or reviewed alias. It is injected rather than
    imported so this module stays independent of how approval is stored, and
    so the safety rule can be tested without a database.

    Returns a dict; ``role_candidate`` is what should be matched, and it falls
    back to the unmodified title whenever stripping would not land on an
    approved name.
    """
    raw = _clean(raw_title)
    core, qualifiers = split_qualifiers(raw)
    stripped, removed, level = peel_modifiers(core)

    multi_role = bool(MULTI_ROLE.search(core))

    # The safety rule. Stripping is allowed only when it reaches something
    # already approved; otherwise the original stands and the title goes to
    # review rather than being reshaped into a role that does not exist.
    candidate, applied, reason = core, [], ""
    if not removed:
        reason = "no rank word present"
    elif multi_role:
        # "Senior IT Lead / IT Supervisor" still names two roles once the
        # rank comes off; resolving it is the JD resolver's job.
        reason = "names more than one role; rank removal cannot disambiguate"
    elif is_approved(stripped):
        candidate, applied = stripped, removed
        reason = "rank removed; remainder is an approved role"
    else:
        reason = ("rank NOT removed: %r is not an approved role or reviewed "
                  "alias" % stripped)

    if level is None and ENTRY_HINT.search(raw):
        level = "ENTRY"

    return {
        "raw_title": raw,
        "normalized_full": core.lower(),
        "role_candidate": candidate.lower(),
        "removed_modifiers": applied,
        "detected_modifiers": removed,
        "seniority_level": level,
        "qualifiers": qualifiers,
        "multi_role": multi_role,
        "decision": reason,
    }
