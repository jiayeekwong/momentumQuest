"""Which resources are related to a skill, and in what order to list them.

Deliberately not a recommender. The page shows a student the courses that
teach a skill and lets them choose; nothing here claims the first entry is the
best one, because nothing here knows that. A course's length, teaching quality
and suitability for one student are not in the catalogue, and an order that
implied otherwise would be asserting more than the evidence carries.

What the order *is* for: putting the clearly-relevant material first. Every
resource here already earned its place -- a resource reaches a skill only when
the canonical extractor found that skill in the course's own words -- so this
sorts admitted material rather than deciding admission.

Two signals, in that order:

1. **Evidence.** A course whose *title* names the skill is about that skill.
   One whose provider lists it under "Skills you'll gain" teaches it. One that
   merely mentions it in prose might be about something else entirely: "5G
   Mobile Networks" reached a Machine Learning recommendation that way, and its
   declared skills are all networking.

2. **The vendor for that skill**, secondarily. Microsoft's own C# material is
   a reasonable thing to put near the top of a C# list. It is not a claim that
   it is the best C# course, and it applies per skill -- Microsoft is not the
   vendor for SAP, so its SAP material gets no such nudge.

``is_free`` is deliberately *not* a signal. Only one provider populates it, so
ranking by it would order by which platform a course came from wearing a
different name. It is displayed where known and hidden where not.
"""

import re
from collections import OrderedDict

from .models import CourseCatalogue, LearningResource

#: How many to show per skill before "View more". Enough to choose between,
#: few enough to read.
DEFAULT_PER_SKILL = 5

#: Coursera cards carry the provider's own list of what a course teaches. It is
#: the strongest evidence available short of the title itself.
DECLARED_SKILLS = re.compile(r"skills? you'?ll gain[:\s]*(.*)",
                             re.IGNORECASE | re.DOTALL)

#: Where that list stops and ordinary prose begins.
#:
#: The list is comma-separated title-case items and contains no sentence stops;
#: the description that follows does. Without this bound the greedy capture ran
#: to the end of the card, so a skill mentioned once in prose read as one the
#: provider had declared -- which is precisely the distinction the tiers exist
#: to draw, and it silently collapsed MENTION into DECLARED.
END_OF_LIST = re.compile(r"\.\s")

TITLE, DECLARED, MENTION, UNKNOWN = 0, 1, 2, 3


def evidence_tier(skill_name, title, card_text, aliases=()):
    """How directly the course's own text supports this skill.

    Lower is stronger. Computed from the stored evidence rather than the
    mapping, so it can be recomputed offline whenever the extractor changes --
    which is the reason card_text is kept in the seed files.

    ``aliases`` matter as much as the canonical name, because the catalogue's
    name for a skill is often not the word a course uses. "iOS (Native)" is 21
    adverts of Malaysian demand with 52 courses, and not one of them is titled
    "iOS (Native)" -- they say "iOS". Checking the canonical name alone put
    every one of those in the weakest band and buried them beneath material
    that merely mentions the skill in passing.
    """
    terms = [skill_name, *aliases]
    lowered_title = (title or "").casefold()
    if any(term.casefold() in lowered_title for term in terms):
        return TITLE
    if not card_text:
        return UNKNOWN

    lowered_card = card_text.casefold()
    declared = DECLARED_SKILLS.search(card_text)
    if declared:
        listed = declared.group(1)
        stop = END_OF_LIST.search(listed)
        if stop:
            listed = listed[:stop.start()]
        listed = listed.casefold()
        if any(term.casefold() in listed for term in terms):
            return DECLARED
    if any(term.casefold() in lowered_card for term in terms):
        return MENTION
    return UNKNOWN


def _interleave_providers(rows):
    """Round-robin across providers, preserving each provider's own order.

    Diversity influences the ordering without ever costing a slot: when one
    provider is the only one with material, its resources simply follow one
    another. A hard cap would have left the list short instead, which serves
    nobody -- a student looking at five slots and one provider wants five
    courses, not three and two gaps.
    """
    by_provider = OrderedDict()
    for row in rows:
        by_provider.setdefault(row.platform, []).append(row)

    ordered = []
    while any(by_provider.values()):
        for queue in by_provider.values():
            if queue:
                ordered.append(queue.pop(0))
    return ordered


def _diversify_within_tiers(tiered):
    """Spread providers inside each evidence tier, never across them.

    Interleaving the whole list would let a provider's weakly-evidenced course
    take a slot ahead of another provider's strongly-evidenced one, which is
    exactly the trade this ordering is meant to refuse. Evidence decides which
    band a resource sits in; diversity only decides the order within a band.
    """
    ordered = []
    for tier in sorted(tiered):
        ordered.extend(_interleave_providers(tiered[tier]))
    return ordered


def related_resources(skill, limit=DEFAULT_PER_SKILL, authority=None):
    """Resources that teach ``skill``, most clearly related first.

    Returns ``(resources, total)`` -- the page's slice and the full count, so
    the caller can offer "View more" without fetching everything. ``limit=None``
    returns all of them, which is what "View more" then asks for.

    Deterministic: the same catalogue produces the same list every time, which
    matters because a student who returns to the page should find what they
    saw, and because a test can assert it.
    """
    rows = list(
        LearningResource.objects
        .filter(skill=skill, is_active=True)
        .select_related("skill")
    )
    if not rows:
        return [], 0

    # One query for the evidence behind all of them, rather than one per row.
    cards = dict(
        CourseCatalogue.objects
        .filter(url__in=[row.url for row in rows])
        .values_list("url", "card_text")
    )
    vendor = (authority or {}).get(skill.skill_name)
    # One query for the names this skill also goes by. Contextual aliases are
    # excluded for the same reason the extractor gates them: a term too weak to
    # match unguarded in an advert is no stronger in a marketing blurb.
    aliases = list(
        skill.aliases.filter(is_active=True, requires_context=False)
        .values_list("alias_name", flat=True)
    )

    tiers = {}
    for row in rows:
        tier = evidence_tier(skill.skill_name, row.title,
                             cards.get(row.url, ""), aliases)
        tiers.setdefault(tier, []).append(row)

    for band in tiers.values():
        band.sort(key=lambda row: (
            # The vendor for this particular skill, second only to evidence.
            0 if row.platform == vendor else 1,
            # Title last, so the order is total and stable between runs. A
            # tie-break, not a quality signal.
            row.title.casefold(),
        ))

    ordered = _diversify_within_tiers(tiers)
    return (ordered if limit is None else ordered[:limit]), len(rows)


def free_status(urls):
    """``{url: True/False}`` for courses whose provider stated a price.

    URLs with no stated price are absent rather than present-and-null: the
    caller shows the field only when it is known, and an absent key is harder
    to render as "Paid" by accident than a None is.
    """
    return {
        url: is_free
        for url, is_free in CourseCatalogue.objects
        .filter(url__in=list(urls))
        .exclude(is_free__isnull=True)
        .values_list("url", "is_free")
    }
