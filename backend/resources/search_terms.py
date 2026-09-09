"""What to type into a course search, given a canonical skill.

The catalogue's canonical name and a good search phrase are not the same
string, and conflating them is why searching for skills would otherwise
under-perform. "RCA" is the canonical skill; typing it into Coursera returns
chemistry and radio-controlled aircraft. "Root Cause Analysis" returns the
courses. "UAT" and "ERP" behave the same way.

So the phrase is derived, and the canonical identity is never altered by it.
The skill remains RCA; only the retrieval device changes. Nothing here decides
what a course *teaches* -- that is settled afterwards from the course's own
text, so a bad phrase costs recall and can never cause a mis-mapping.

Two sources, in order:

1. The reviewed alias table. It already holds exactly the expansions needed --
   UAT -> "User Acceptance Testing", RCA -> "Root Cause Analysis",
   ERP -> "Enterprise Resource Planning" -- because somebody reviewed them for
   the extractor. Deriving from it means the phrases are versioned in the seed
   files, stay in sync, and never become a second list to maintain.

2. A small override map, for the cases evidence contradicts the alias table.
   Every entry carries its reason.
"""

import re

#: Canonical names that search badly no matter what the alias table says, with
#: the reason each is here. Deliberately short: an override is a claim that the
#: reviewed data is wrong for retrieval, and each one should be defensible.
SEARCH_OVERRIDES = {
    # Bare "ABAP" works, but the courses are titled "SAP ABAP ..." and the
    # vendor prefix pulls the whole S/4HANA specialization in with them.
    "ABAP": "SAP ABAP",
    # "C#" alone is mangled by search tokenisers that drop the '#'; adding the
    # domain word keeps the results on the language.
    "C#": "C# programming",
    "C++": "C++ programming",
    # ".NET" alone returns networking courses ('.net' reads as a domain).
    ".NET": ".NET development",
    # "R" and "Go" are single words with enormous non-technical usage.
    "R": "R programming language",
    "Go": "Go programming language",
    # "Jira" is a product name and searches cleanly, but the courses are about
    # using it to run projects.
    "Jira": "Jira project management",
    # The longest-alias rule picks "SAP Business One" here, which is one SMB
    # product rather than the vendor. "SAP" already searches well on its own,
    # so the expansion is refused rather than narrowed.
    "SAP": "SAP",
    # YAML's only alias is "yaml ain't markup language" -- the recursive-acronym
    # joke, which is what the format is *called* and not what any course is
    # titled. It was the last query still failing after two acquisition rounds:
    # a phrase no search engine can satisfy fails rather than returning
    # nothing, so it never resolved itself.
    #
    # The general lesson, and the reason this override exists rather than a
    # rule: an expansion is only better when it is what people write. The
    # longest alias is a good proxy for that and not a guarantee.
    "YAML": "YAML",
}

#: An abbreviation for these purposes: short, and not obviously a word. Used
#: only to decide whether a longer alias is likely to search better.
_ABBREVIATION = re.compile(r"^[A-Z0-9./+#-]{2,6}$")


def looks_like_abbreviation(name):
    """Whether the canonical name reads as an acronym rather than a phrase.

    "UAT", "RCA", "ERP", "SQL" yes; "Microsoft SQL Server", "Networking" no.
    Case matters: an all-caps short token is the signal.
    """
    return bool(_ABBREVIATION.match(name)) and " " not in name


def expansion_for(skill, aliases):
    """The longest active alias that plausibly spells the name out.

    Longest wins because the expansion is the informative one: SAP's aliases
    are "SAP B1", "SAP Business One", "SAP ERP", and the middle one is the
    phrase a course would use.
    """
    candidates = [
        alias for alias in aliases
        # An expansion contains a space and is longer than the abbreviation.
        # "MSSQL" is another abbreviation, not an expansion of one.
        if " " in alias and len(alias) > len(skill)
    ]
    return max(candidates, key=len) if candidates else None


def search_phrase(skill_name, aliases=()):
    """The phrase to search for one canonical skill.

    ``aliases`` are that skill's active alias names. Contextual aliases are the
    caller's to filter -- this function does not read the database, so it can be
    tested without one.
    """
    if skill_name in SEARCH_OVERRIDES:
        return SEARCH_OVERRIDES[skill_name]

    if looks_like_abbreviation(skill_name):
        expansion = expansion_for(skill_name, aliases)
        if expansion:
            return expansion

    return skill_name


def phrases_for_skills(skills):
    """``(skill_name, phrase)`` for each Skill, in the order given.

    Contextual aliases are excluded: an alias flagged as too weak to match
    unguarded in an advert is no better as a search phrase, and using one would
    quietly widen a search the reviewer had narrowed.
    """
    pairs = []
    for skill in skills:
        aliases = [
            alias.alias_name
            for alias in skill.aliases.all()
            if alias.is_active and not alias.requires_context
        ]
        pairs.append((skill.skill_name, search_phrase(skill.skill_name, aliases)))
    return pairs
