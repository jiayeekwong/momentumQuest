import re

from .models import Skill, SkillAlias

#: Skill names that are also ordinary English words, abbreviations of
#: something else, or single letters. A word-boundary match alone says nothing
#: about them: "go" appears in "go live" and "go-to person", "R" in "R&D",
#: "Swift" in "swift resolution of customer issues" and in SWIFT the banking
#: network. Left unguarded these produced most of their own matches -- "Go"
#: was tagged on 40 adverts and "R" on 23, and a SAP consultant's skill gap
#: told the student to learn Go and Swift.
#:
#: A name listed here is only accepted when the surrounding text also reads as
#: technical, and never when one of its known idioms is what matched.
AMBIGUOUS_SKILLS = {"go", "r", "c", "swift", "rust", "dart", "scala", "spark",
                    "math", "excel", "jest", "solid", "bert", "keras", "vite",
                    # Added after the Phase 10 shadow run: "SDN" matched the
                    # company suffix "Sdn Bhd" in 53 of 53 adverts, and "GIS"
                    # is Group Information Security in Malaysian banking.
                    "sdn", "gis"}

#: How much text either side of a match is inspected for context.
CONTEXT_WINDOW = 70

#: Phrases that are the *reason* an ambiguous name matched, and are not the
#: skill. Checked against the matched term plus its immediate surroundings.
NEGATIVE_CONTEXT = (
    r"\bgo[-\s]?live\b", r"\bgo[-\s]to\b", r"\bgo\s+the\s+extra\b",
    r"\bgo\s+through\b", r"\bgo\s+beyond\b", r"\bgo\s+above\b",
    r"\bon\s+the\s+go\b", r"\bready\s+to\s+go\b", r"\bgo\s+into\b",
    r"\br\s*&\s*d\b", r"\br\.\s*i\.\s*v\.\s*e\.\s*r\b",
    r"\bswift\s+(?:resolution|response|action|turnaround|manner|delivery)\b",
    r"\bswift\s+(?:message|payment|network|code|mt\d)", r"\biso\s*20022\b",
    r"\bexcel(?:s|led|lent|ling)?\s+(?:in|at)\b",
    r"\bsolid\s+(?:understanding|knowledge|experience|grasp|background|foundation)\b",
    r"\bspark\s+(?:interest|joy|innovation|creativity)\b",
    r"\bc\s*-?\s*level\b", r"\bcertificate\s+in\s+c\b",
    # "Sdn Bhd" -- Sendirian Berhad -- ends the name of virtually every
    # Malaysian company. It is not Software Defined Networking, and without
    # this it produced 53 false SDN detections out of 53.
    r"\bsdn\.?\s*bhd\b",
    # "Solid SQL Server skills", "2 solid years" -- the adjective, not the
    # design principles. SOLID the acronym sits next to "principles".
    r"\bsolid\s+(?!principles?\b|design\b)\w+",
    r"\b\d+\s+solid\b",
    # "solid, practical knowledge" -- the comma escapes the rule above.
    r"\bsolid\s*[,;]",
    # Solid.js is a JavaScript framework, not the SOLID principles.
    r"\bsolid\.js\b",
    # In Malaysian banking adverts GIS is routinely Group Information
    # Security, a policy function, not geographic information systems.
    r"\bgis\s+(?:strategy|guideline|policy|standard|framework)\b",
)
NEGATIVE_PATTERN = re.compile("|".join(NEGATIVE_CONTEXT), re.IGNORECASE)

#: Signals that the surrounding text is discussing technology, so an
#: ambiguous name in it plausibly means the skill. Deliberately broad: the
#: negative list above is what does the precise work, and this only has to
#: separate a requirements paragraph from prose about attitude.
POSITIVE_CONTEXT = re.compile(
    r"\b(?:programming|language|framework|library|developer|development|"
    r"engineer|engineering|software|backend|back[- ]end|frontend|front[- ]end|"
    r"full[- ]?stack|script|scripting|code|coding|codebase|api|sdk|stack|"
    r"proficien\w*|hands[- ]on|familiar\w*|knowledge\s+of|experience\s+(?:with|in)|"
    r"python|java|javascript|typescript|kotlin|flutter|ios|android|xcode|swift|"
    r"golang|node|react|angular|vue|django|flask|spring|\.net|sql|linux|docker|"
    r"kubernetes|aws|azure|gcp|git|matlab|sas|tableau|power\s?bi|statistic\w*|"
    r"data\s+(?:analysis|science|engineering)|machine\s+learning)\b",
    re.IGNORECASE,
)


def _accepted_in_context(text, match):
    """Whether an ambiguous match is really the skill, given its surroundings."""
    start = max(0, match.start() - CONTEXT_WINDOW)
    window = text[start:match.end() + CONTEXT_WINDOW]

    # An idiom that explains the match rules it out, wherever it sits.
    if NEGATIVE_PATTERN.search(window):
        return False
    return bool(POSITIVE_CONTEXT.search(window))


#: How a term was matched, recorded per job_skill link so a questionable
#: detection can be traced back to the exact string that produced it.
DIRECT_CANONICAL = "DIRECT_CANONICAL"
ALIAS = "ALIAS"
CONTEXTUAL_ALIAS = "CONTEXTUAL_ALIAS"


def _terms_by_skill():
    """Every term that may match, with how it should be treated.

    Inactive skills and aliases are excluded rather than deleted: an imported
    name awaiting review must stay recoverable, but it must not create job
    links in the meantime. Phase 9 showed what happens otherwise -- an
    inactive alias "xml" pointing at the Python library lxml very nearly
    filed Malaysian XML demand under a parser.
    """
    terms = {}
    for skill in Skill.objects.filter(is_active=True):
        terms[skill] = [(skill.skill_name, DIRECT_CANONICAL)]
    for alias in (SkillAlias.objects
                  .filter(is_active=True, skill__is_active=True)
                  .select_related("skill")):
        entry = terms.setdefault(alias.skill,
                                 [(alias.skill.skill_name, DIRECT_CANONICAL)])
        entry.append((alias.alias_name,
                      CONTEXTUAL_ALIAS if alias.requires_context else ALIAS))
    return terms


# Characters that continue a technology token. A term must not be glued to one
# of these, which is what \b means for ordinary words and what it fails to mean
# for terms whose own edge is punctuation.
#
# The two sides differ by the dot, and not arbitrarily. On the left it must
# block a match: ".NET" inside "ASP.NET" is the web framework, a different
# catalogue entry. On the right it must not, because a dot after a term is
# usually the end of a sentence -- "Java/C#. Understanding of REST APIs"
# was the whole reason two adverts still missed C# after the boundary fix.
_LEFT_TOKEN_CHARS = r'\w#+.'
_RIGHT_TOKEN_CHARS = r'\w#+'


def _term_pattern(term):
    """A boundary-anchored pattern that also works for C#, C++ and .NET.

    ``\\b`` is the edge between a word character and a non-word one, so
    ``\\bC#\\b`` cannot match "C# developer": after the '#' comes a space,
    and two non-word characters have no boundary between them. The same defeats
    C++ and .NET. It was not a near miss -- 64 adverts mentioned C# and not one
    produced a skill link, and .NET appeared in 57 with no catalogue row at all.

    Where the term's own edge is punctuation, the assertion is replaced with
    the one \\b was standing in for: not adjacent to more of the same token.
    So "C#" matches in "C# developer" but not in "C##", and ".NET" matches on
    its own but not inside "ASP.NET", which is a different skill.
    """
    left = (r'\b' if (term[:1].isalnum() or term[:1] == '_')
            else rf'(?<![{_LEFT_TOKEN_CHARS}])')
    right = (r'\b' if (term[-1:].isalnum() or term[-1:] == '_')
             else rf'(?![{_RIGHT_TOKEN_CHARS}])')
    return re.compile(left + re.escape(term) + right, re.IGNORECASE)


def extract_skill_matches(text):
    """Every skill the text asks for, with the evidence for each.

    Returns a list of ``(skill, matched_text, match_method)``. The method
    matters downstream: a CONTEXTUAL_ALIAS hit survived a look at its
    surroundings, an ALIAS hit did not need to, and a reviewer reading a
    suspicious link needs to know which.

    Three gates, in order of how much they are trusted:

      * a canonical name in AMBIGUOUS_SKILLS ("Go", "R", "Swift") must survive
        the context check -- these are ordinary English words;
      * an alias marked ``requires_context`` must survive the same check --
        that flag exists for short or overloaded strings like "Mac", which is
        macOS in one advert and a MAC address in another;
      * everything else matches on a word boundary alone.
    """
    if not text:
        return []

    terms_by_skill = _terms_by_skill()

    # A catalogue of two thousand skills makes the naive "compile a pattern
    # per skill and scan the text" loop the dominant cost of every extraction.
    # This containment test is a pure filter, not a second matching rule: the
    # patterns below are anchored on both sides, so they can only match where
    # the term already occurs as a substring.
    lowered = text.lower()

    matches = []
    for skill, terms in terms_by_skill.items():
        if not any(term.lower() in lowered for term, _ in terms):
            continue

        ambiguous_name = skill.skill_name.strip().lower() in AMBIGUOUS_SKILLS
        best = None
        for term, method in terms:
            if term.lower() not in lowered:
                continue
            pattern = _term_pattern(term)
            gated = (method == CONTEXTUAL_ALIAS
                     or (method == DIRECT_CANONICAL and ambiguous_name))

            for found in pattern.finditer(text):
                if gated and not _accepted_in_context(text, found):
                    continue
                candidate = (found.group(0), method)
                # An ungated canonical hit is the strongest evidence there is;
                # take it and stop looking.
                if not gated and method == DIRECT_CANONICAL:
                    best = candidate
                    break
                best = best or candidate
            if best and best[1] == DIRECT_CANONICAL:
                break

        if best is not None:
            matches.append((skill, best[0], best[1]))

    return matches


def extract_skills_from_text(text):
    """The skills a text asks for.

    Thin wrapper over :func:`extract_skill_matches`, kept because most callers
    only want the skills and should not have to unpack match provenance.
    """
    return [skill for skill, _, _ in extract_skill_matches(text)]
