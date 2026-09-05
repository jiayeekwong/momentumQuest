"""Assigning a Market Role to a scraped advert.

    Raw Job Title -> Normalized Job Title -> Market Role

Every tier here is exact: a normalized title either *is* a Market Role name,
*is* a reviewed alias, or is not. Nothing is assigned by edit distance, word
overlap, embeddings or any other similarity measure. Similarity may rank
suggestions for a person to review (MarketRoleCandidate), but a machine may
never turn a resemblance into a career shown to a student.

Precision is preferred to coverage throughout. AMBIGUOUS and UNCLASSIFIED are
correct answers, and an advert that cannot be placed is left unplaced rather
than pushed into the nearest role -- these classifications go on to build
role-level skill demand, and one wrongly-filed advert quietly corrupts the
skill profile a student is measured against.
"""

import re
from collections import namedtuple

from .title_normalizer import (
    normalize_title,
    title_segments,
    title_without_career_level,
)

METHOD_EXACT = "EXACT_MARKET_ROLE"
METHOD_ALIAS = "REVIEWED_TITLE_ALIAS"
METHOD_LEVEL_ROLE = "CAREER_LEVEL_NORMALIZED_ROLE"
METHOD_LEVEL_ALIAS = "CAREER_LEVEL_NORMALIZED_ALIAS"
METHOD_SEGMENT = "REVIEWED_SEGMENT_MATCH"
METHOD_JD = "JD_RESOLVED"
METHOD_AMBIGUOUS = "AMBIGUOUS"
METHOD_UNCLASSIFIED = "UNCLASSIFIED"


#: Titles that name a department rather than a job. The same wording covers
#: genuinely different work at different Malaysian employers -- one "IT
#: Executive" rebuilds laptops, the next configures firewalls -- so the same
#: Normalized Job Title is *not* necessarily the same Market Role. These never
#: receive a title alias; they go to advert-level resolution or stay
#: unclassified. Matched against the career-level-normalized title.
AMBIGUOUS_TITLES = frozenset({
    # "IT <grade>" -- the department plus a rank, naming no function at all.
    "information technology executive",
    "information technology manager",
    "information technology engineer",
    "information technology officer",
    "information technology specialist",
    "information technology consultant",
    "information technology analyst",
    "information technology assistant",
    "information technology administrator",
    "information technology operations executive",
    "information technology operations analyst",
    "information technology resident engineer",
    "information technology euc engineer",
    "information technology demand manager",
    "information technology outsourcing supervisor",
    "assistant information technology manager",
    "information technology manager assistant manager",
    "executive information technology",
    "analyst information technology",
    "information technology and digital",
    # Infrastructure-or-support generalist posts: the same wording covers a
    # network engineer at one employer and a helpdesk at the next.
    "information technology infrastructure executive",
    "information technology infrastructure and support executive",
    "information technology infrastructure and support",
    "information technology infrastructure and network",
    "information technology systems and infrastructure executive",
    "information technology cloud infrastructure specialist",
    "information technology security and infrastructure specialist",
    "executive information technology and system control",
    "executive information technology operations and systems support",
    # Generic grades with no domain at all.
    "technical executive",
    "technology executive",
    "business systems executive",
    "application specialist",
    "computer operator",
    "support engineer",
    "staff engineer",
    "operations executive",
    "business consultant",
    "system consultant",
})


ClassificationResult = namedtuple(
    "ClassificationResult",
    "market_role method matched_alias evidence candidates",
)


def unclassified(candidates=()):
    return ClassificationResult(None, METHOD_UNCLASSIFIED, "", "", tuple(candidates))


class MarketRoleIndex:
    """Exact lookups from a Normalized Job Title to a Market Role.

    Built once per classification run. ``by_role`` and ``by_alias`` are kept
    apart so the tier that produced a match is reportable, which is the whole
    point of storing a classification method.
    """

    def __init__(self, by_role, by_alias, alias_notes):
        self.by_role = by_role
        self.by_alias = by_alias
        self.alias_notes = alias_notes

    def lookup(self, key):
        """(role, method_kind) for an exact key, or (None, None).

        method_kind is "role" or "alias" -- the caller decides whether the key
        was the raw normalized title or its career-level-normalized form, and
        names the tier accordingly.
        """
        if not key:
            return None, None
        role = self.by_role.get(key)
        if role is not None:
            return role, "role"
        role = self.by_alias.get(key)
        if role is not None:
            return role, "alias"
        return None, None


def build_index(roles=None, aliases=None):
    from .models import MarketRole, MarketRoleAlias

    if roles is None:
        roles = MarketRole.objects.filter(is_active=True)
    if aliases is None:
        # Every control the alias table carries is applied here, not just
        # ``reviewed``. Each one exists to stop a row classifying adverts, and
        # a control the resolver does not read is not a control:
        #
        #   is_active=False       a retired alias, kept for history
        #   review_status         REJECTED means a person looked and said no;
        #                         PENDING means nobody has looked yet
        #   requires_body_context an alias too weak to fire on the title alone
        #
        # The last one is excluded rather than deferred because nothing reads
        # it yet: resolve_from_description scores the advert against the body
        # rules and consults index.by_role only, so a body-context alias has no
        # consumer. Leaving it in the title index would make the flag mean the
        # opposite of what it says.
        aliases = (MarketRoleAlias.objects
                   .filter(reviewed=True,
                           is_active=True,
                           review_status=MarketRoleAlias.ReviewStatus.APPROVED,
                           requires_body_context=False,
                           market_role__is_active=True)
                   .select_related("market_role"))

    by_role, by_alias, notes = {}, {}, {}
    for role in roles:
        key = role.normalized_name or normalize_title(role.name)
        if key:
            by_role[key] = role
    for alias in aliases:
        key = alias.normalized_title
        # A reviewed alias never shadows a Market Role's own name.
        if key and key not in by_role:
            by_alias[key] = alias.market_role
            notes[key] = alias.notes
    return MarketRoleIndex(by_role, by_alias, notes)


def _segment_roles(raw_title, index):
    """Distinct Market Roles named by the segments of a compound title.

    "Assistant Manager, IT Business Analyst" splits into two segments, one of
    which is a reviewed Business Analyst alias. Only whole segments are looked
    up -- never a substring of one -- so "Data Centre Project Assistant" can
    never be claimed by an unrelated role that happens to share a word.
    """
    found = {}
    for segment in title_segments(raw_title):
        for key in (normalize_title(segment),
                    title_without_career_level(segment),
                    title_without_career_level(segment, strip_associate=True)):
            role, _kind = index.lookup(key)
            if role is not None:
                found.setdefault(role.id, (role, key))
                break
    return found


def classify_title(raw_title, index):
    """Classify from the title alone.

    Returns a ClassificationResult. A result whose method is AMBIGUOUS or
    UNCLASSIFIED carries no Market Role and is the caller's cue to try
    advert-level resolution.
    """
    normalized = normalize_title(raw_title)
    levelled = title_without_career_level(raw_title)
    associate = title_without_career_level(raw_title, strip_associate=True)

    # 1/2. The title as advertised is a Market Role name or a reviewed alias.
    role, kind = index.lookup(normalized)
    if role is not None:
        method = METHOD_EXACT if kind == "role" else METHOD_ALIAS
        return ClassificationResult(role, method, normalized,
                                    index.alias_notes.get(normalized, ""), ())

    # A department title is ambiguous even when a level sits in front of it:
    # "Senior IT Executive" is no more specific than "IT Executive".
    if levelled in AMBIGUOUS_TITLES or normalized in AMBIGUOUS_TITLES:
        return ClassificationResult(None, METHOD_AMBIGUOUS, levelled or normalized,
                                    "Title names a department rather than a "
                                    "career function", ())

    # 3/4. Same two lookups once genuine career levels are removed.
    for key in (levelled, associate):
        if not key or key == normalized:
            continue
        role, kind = index.lookup(key)
        if role is not None:
            method = METHOD_LEVEL_ROLE if kind == "role" else METHOD_LEVEL_ALIAS
            return ClassificationResult(role, method, key,
                                        index.alias_notes.get(key, ""), ())

    # 5. A compound title containing exactly one recognisable Market Role.
    found = _segment_roles(raw_title, index)
    if len(found) == 1:
        role, key = next(iter(found.values()))
        return ClassificationResult(role, METHOD_SEGMENT, key,
                                    index.alias_notes.get(key, ""), ())
    if len(found) > 1:
        names = sorted(r.name for r, _k in found.values())
        return ClassificationResult(
            None, METHOD_AMBIGUOUS, "",
            "Title names more than one career: " + ", ".join(names),
            tuple(r for r, _k in found.values()))

    return unclassified()


# --- Advert-level resolution ----------------------------------------------
#
# Only reached for titles that name a department rather than a job. The
# employer is not required to write "As a Software Engineer..." -- consistent
# functional responsibility evidence is enough. What is required is that the
# evidence be *functional*: what the person does, what they are accountable
# for, what systems they handle.
#
# Technologies are supporting evidence only, never decisive on their own.
# Python does not mean Data Scientist and AWS does not mean Cloud Engineer;
# the same tools appear across most ICT careers. That restraint also keeps the
# pipeline honest downstream, because these same advertised technologies are
# what later become the Market Role's skill demand -- classifying a role *by*
# its technologies and then measuring its technologies would be circular.

#: role name -> (function phrases, supporting phrases)
JD_RULES = {
    "IT Support": (
        (r"end[- ]user support", r"helpdesk", r"help desk", r"service desk",
         r"troubleshoot(?:ing)? (?:user|employee|staff|laptop|desktop|pc|computer)",
         r"(?:install|setup|set up|configure)[a-z ]{0,12}(?:software|application|laptop|desktop|workstation)",
         r"(?:resolve|handle|manage|log)[a-z ]{0,12}ticket",
         r"user account", r"password reset", r"onboarding of (?:new )?stff|staff onboarding",
         r"hardware (?:maintenance|repair|replacement)", r"printer",
         r"first[- ]?level support", r"level 1 support", r"l1 support",
         r"desktop support", r"it equipment"),
        (r"windows", r"office 365", r"microsoft office", r"antivirus",
         r"asset (?:inventory|tagging)", r"remote desktop"),
    ),
    "Network Engineer": (
        (r"\brouters?\b", r"\bswitch(?:es)?\b", r"\bfirewalls?\b",
         r"\blan\b", r"\bwan\b", r"network (?:monitoring|troubleshooting|"
         r"configuration|performance|infrastructure|security|design)",
         r"\bvpn\b", r"network device", r"routing (?:and|&) switching",
         r"bandwidth", r"network topology"),
        (r"\bcisco\b", r"\bfortigate\b", r"\bmikrotik\b", r"\btcp/ip\b",
         r"\bbgp\b", r"\bospf\b", r"\bvlan\b"),
    ),
    "Infrastructure Engineer": (
        (r"server (?:administration|management|maintenance|provisioning|"
         r"deployment|monitoring)", r"active directory", r"virtuali[sz]ation",
         r"backup and (?:recovery|restore)", r"disaster recovery",
         r"storage (?:management|system)", r"patch(?:ing| management)",
         r"system administration", r"infrastructure (?:support|maintenance|"
         r"management|monitoring)", r"data cent(?:er|re) infrastructure"),
        (r"\bvmware\b", r"\bhyper-?v\b", r"\bwindows server\b", r"\blinux\b",
         r"\besxi\b", r"\bnas\b", r"\bsan\b"),
    ),
    "Application Support Analyst": (
        (r"application support", r"production support",
         r"incident (?:management|resolution|handling)",
         r"(?:l2|l3|level 2|level 3) support", r"root cause analysis",
         r"escalat(?:e|ion)[a-z ]{0,20}(?:vendor|development team)",
         r"service level agreement", r"\bsla\b",
         r"monitor(?:ing)? (?:the )?application", r"user acceptance test"),
        (r"\bitil\b", r"\bjira\b", r"\bservicenow\b", r"\bsql\b"),
    ),
    "Software Engineer": (
        (r"(?:develop|design|build|write)[a-z ]{0,20}(?:software|application|"
         r"system|module|feature|api)", r"source code", r"code review",
         r"unit test", r"software development life ?cycle", r"\bsdlc\b",
         r"debug(?:ging)? (?:code|application|software)",
         r"version control", r"technical specification",
         r"api (?:development|integration)"),
        (r"\bgit\b", r"\bjava\b", r"\bpython\b", r"\b\.net\b", r"\bspring\b",
         r"\breact\b", r"\bagile\b", r"\bscrum\b"),
    ),
    "Data Analyst": (
        (r"data (?:analysis|analytics|visuali[sz]ation|quality|cleansing)",
         r"(?:build|develop|prepare|produce)[a-z ]{0,20}(?:dashboard|report)",
         r"business insight", r"\bkpi\b", r"trend analysis",
         r"stakeholder report", r"data[- ]driven (?:decision|insight)"),
        (r"\bsql\b", r"power ?bi", r"\btableau\b", r"\bexcel\b", r"\bpandas\b"),
    ),
    "Security Analyst": (
        (r"security (?:incident|monitoring|operations|assessment|awareness|"
         r"policy|compliance)", r"vulnerability (?:assessment|management|scan)",
         r"penetration test", r"threat (?:detection|intelligence|hunting)",
         r"security event", r"iso ?27001", r"access (?:control|review) "
         r"(?:management|process)?", r"risk assessment"),
        (r"\bsiem\b", r"\bsoc\b", r"\bfirewall\b", r"\bnessus\b", r"\bsplunk\b"),
    ),
}

#: An advert must state this many *distinct* functional responsibilities for a
#: Market Role before it is assigned one. Three, because two can be incidental
#: -- almost every ICT advert mentions a ticket and a laptop somewhere.
JD_MINIMUM_FUNCTION_MATCHES = 3

#: And it must beat the runner-up by this much, so an advert describing two
#: jobs equally stays ambiguous rather than tipping on a single phrase.
JD_REQUIRED_MARGIN = 2

#: Supporting technology evidence counts, but at half weight and never alone.
JD_SUPPORT_WEIGHT = 0.5


def _score_description(text, rules=None):
    """[(score, function_hits, role_name, evidence)] best first."""
    rules = JD_RULES if rules is None else rules
    body = " ".join((text or "").lower().split())
    if not body:
        return []

    scored = []
    for role_name, (functions, supports) in rules.items():
        hits, evidence = [], []
        for pattern in functions:
            found = re.search(pattern, body)
            if found:
                hits.append(pattern)
                evidence.append(found.group(0).strip())
        support_hits = sum(1 for pattern in supports if re.search(pattern, body))
        if not hits:
            continue
        score = len(hits) + support_hits * JD_SUPPORT_WEIGHT
        scored.append((score, len(hits), role_name, evidence))
    scored.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return scored


def resolve_from_description(text, index, rules=None):
    """Classify an ambiguous advert from its stated responsibilities.

    Returns a ClassificationResult; UNCLASSIFIED whenever the advert does not
    describe one job clearly enough, which is the common case and the correct
    answer for it.
    """
    scored = _score_description(text, rules)
    if not scored:
        return unclassified()

    score, functions, role_name, evidence = scored[0]
    if functions < JD_MINIMUM_FUNCTION_MATCHES:
        return unclassified()

    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    if score - runner_up < JD_REQUIRED_MARGIN:
        candidates = [index.by_role.get(normalize_title(row[2])) for row in scored[:3]]
        return ClassificationResult(
            None, METHOD_AMBIGUOUS, "",
            "Advert describes more than one career: "
            + ", ".join(row[2] for row in scored[:2]),
            tuple(role for role in candidates if role is not None))

    role = index.by_role.get(normalize_title(role_name))
    if role is None:
        return unclassified()
    return ClassificationResult(
        role, METHOD_JD, "",
        "%d functional responsibilities matched: %s"
        % (functions, "; ".join(evidence[:6])), ())


def classify_listing(raw_title, description, index):
    """The full pipeline for one advert: title first, advert evidence second.

    Advert evidence is read *only* for a title that names a department rather
    than a job. That gate is the difference between resolving an ambiguity and
    inventing a classification: "Data Centre Manager" and "Assistant IT
    Project Manager" both say plainly what they are, and letting the
    responsibilities outvote the title filed them as Application Support
    Analyst and Software Engineer respectively. An unmapped title is a gap in
    the reviewed mapping, to be closed by review -- not by the classifier
    guessing from the body text.
    """
    result = classify_title(raw_title, index)
    if result.market_role is not None:
        return result
    if result.candidates:
        # The title itself named two careers. The advert cannot break that tie
        # without picking one of two jobs it is genuinely advertising.
        return result
    if result.method != METHOD_AMBIGUOUS:
        return result

    resolved = resolve_from_description(description, index)
    if resolved.method == METHOD_UNCLASSIFIED:
        # A department title whose advert says nothing specific enough stays
        # ambiguous. That is the honest answer, not a failure to classify.
        return result
    return resolved
