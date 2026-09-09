"""Which provider is the vendor for which skill -- a Skill x Provider fact.

Not a property of a provider, and emphatically not a property of a resource.

"Microsoft Learn is authoritative" is false as stated. Microsoft Learn is
authoritative for C#, .NET and Azure, and is an ordinary third party for SAP --
its "Planning and Deploying SAP on Azure" is a real course that legitimately
mentions SAP, and none of that makes Microsoft the reference for SAP. A flag on
the provider would say otherwise, and a flag on the resource would freeze the
answer at the moment the row was written, so the fact belongs to the *pair*.

Two rules this module exists to keep separate:

1. **Authority orders; evidence admits.** A resource reaches a skill only by
   the canonical extractor finding that skill in the course's own words. This
   module never adds a mapping, never removes one, and is not consulted while
   mapping happens. It sorts what mapping already produced.

2. **Authority is claimed per technology.** Each adapter declares the skills it
   vendors, next to the code that knows them. This module composes those
   declarations into the Skill x Provider index and refuses to let two
   providers claim the same skill silently.
"""

import logging

logger = logging.getLogger(__name__)

#: Ranks, lowest first. Deliberately coarse: this is a tie-break between
#: resources that all already earned their mapping, not a scoring system.
VENDOR = 0
NON_VENDOR = 1


def authority_index(providers):
    """{skill_name: provider_name} built from what each adapter claims.

    A skill claimed by two providers is a review question, not something to
    resolve by ordering -- both claims are recorded in the log and the first
    registered wins, so the conflict is visible rather than arbitrary and
    silent.
    """
    index = {}
    for provider in providers:
        if not getattr(provider, "is_vendor", False):
            continue
        for skill_name in getattr(provider, "vendor_for", ()):
            existing = index.get(skill_name)
            if existing and existing != provider.name:
                logger.warning(
                    "Vendor authority for %r claimed by both %s and %s; "
                    "keeping %s. One of the two claims is wrong.",
                    skill_name, existing, provider.name, existing)
                continue
            index[skill_name] = provider.name
    return index


def is_authoritative(skill_name, provider_name, index):
    """Whether this provider is the vendor for this specific skill."""
    return index.get(skill_name) == provider_name


def preference_rank(skill_name, provider_name, index):
    """Where a resource sits when recommending for one skill.

    Called with a skill *and* a provider because neither alone answers it. The
    same Microsoft Learn resource ranks first for C# and mid-table for SAP, and
    that is the intended behaviour rather than an inconsistency.
    """
    return VENDOR if is_authoritative(skill_name, provider_name, index) else NON_VENDOR


def rank_resources(skill_name, resources, index, key=None):
    """Order resources for one skill, vendor material first.

    Ordering only. Nothing is filtered and nothing is added: every resource
    passed in already mapped to this skill on its own evidence, and a
    non-vendor resource still appears -- often it is the better course, and
    for most skills no vendor exists at all.
    """
    key = key or (lambda row: row)

    def sort_key(row):
        item = key(row)
        provider = item.get("provider") or item.get("platform") or ""
        # Free before paid within a rank, and unknown price last of the three:
        # a student cannot act on a price nobody stated.
        free = item.get("is_free")
        return (
            preference_rank(skill_name, provider, index),
            {True: 0, False: 1, None: 2}[free if free in (True, False) else None],
            item.get("title") or "",
        )

    return sorted(resources, key=sort_key)
