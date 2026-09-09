"""One shape for what every provider returns, checked at the boundary.

Providers differ in what they publish. Coursera gives a card with a
"Skills you'll gain" list; Microsoft Learn gives a prose summary and no skills
list at all, and buries certification text in a different field again; a
sitemap-backed provider gives a URL and whatever the page carries. If each
adapter were free to shape its own rows, the catalogue would hold a dialect per
provider and every consumer -- the mapper, the seed exporter, the UI -- would
have to learn all of them.

So adapters produce evidence in one shape, and this module is where that shape
is enforced. It normalises rather than trusts: a provider that omits a field
gets a documented default, and a provider that returns something unusable is
rejected here with a reason rather than silently storing a blank row.

What it deliberately does not do is interpret. No skill matching, no guessing
at free/paid from the price text, no inferring a type from the URL. Those are
either the provider's own statement or the extractor's decision, and a
normalizer that quietly invents either is a third source of truth.
"""

#: Every field a normalised course carries, and what it means.
#:
#:   url            the provider's stable identity, already canonicalised
#:   title          what the provider calls it
#:   description    the provider's own words, the evidence a mapping rests on
#:   provider       who published it; stable, because rows are keyed by it
#:   type           Course, Specialization, Certification, Module, Path ...
#:   is_free        True / False / None where the provider does not say
#:   discovered_via the queries that surfaced it, as retrieval provenance
REQUIRED_FIELDS = ("url", "title", "provider")
OPTIONAL_DEFAULTS = {
    "description": "",
    "type": "Course",
    "is_free": None,
    "is_active": True,
    "discovered_via": (),
}

#: Storage limits, applied here so a provider cannot overflow a column and so
#: two providers truncate identically.
MAX_TITLE = 255
MAX_DESCRIPTION = 2000

#: A title shorter than this is navigation furniture, not a course. Coursera's
#: markup yields "Free", "New" and "Beta" as link text on result cards.
MIN_TITLE = 5


class InvalidCourse(ValueError):
    """A provider row that cannot become a catalogue entry, and why."""


def normalize_course(row):
    """One provider row as a catalogue entry, or raise InvalidCourse.

    Raising rather than returning None: a provider producing unusable rows is
    a bug in that adapter, and a caller that silently drops them makes it
    invisible. The acquisition runner catches these per row and reports a
    count, so a broken adapter shows up as a number rather than as an empty
    catalogue nobody can explain.
    """
    missing = [field for field in REQUIRED_FIELDS if not (row.get(field) or "").strip()]
    if missing:
        raise InvalidCourse(f"missing {', '.join(missing)}: {row!r:.120}")

    title = " ".join(str(row["title"]).split())
    if len(title) < MIN_TITLE:
        raise InvalidCourse(f"title too short to be a course: {title!r}")

    url = str(row["url"]).strip()
    if not url.startswith("http"):
        raise InvalidCourse(f"url is not absolute: {url!r}")

    normalised = {
        "url": url,
        "title": title[:MAX_TITLE],
        # Whitespace collapsed because it is compared, hashed into seed
        # digests, and read by a human in a diff. A description that differs
        # only by line breaks is not a change.
        "description": " ".join(str(row.get("description") or "").split())[:MAX_DESCRIPTION],
        "provider": str(row["provider"]).strip(),
        "type": (str(row.get("type") or "").strip()
                 or OPTIONAL_DEFAULTS["type"]),
        "is_free": _normalise_is_free(row.get("is_free")),
        # False for material a provider still publishes but nobody should be
        # sent to -- a retired certification, say. Recorded rather than
        # dropped: the evidence stays reviewable, and mapping skips it.
        "is_active": bool(row.get("is_active", True)),
        # Sorted and de-duplicated: the set of queries that found a course is
        # what matters, not the order they ran in, and an unordered field would
        # make the seed files churn between runs.
        "discovered_via": sorted({
            " ".join(str(phrase).split())
            for phrase in (row.get("discovered_via") or ())
            if str(phrase).strip()
        }),
    }
    return normalised


def _normalise_is_free(value):
    """True, False, or None -- never a string, and never inferred.

    None is a real answer meaning "the provider does not say", and it must
    survive: turning an unknown price into False would tell a student a free
    course costs money.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in ("true", "free", "1", "yes"):
        return True
    if text in ("false", "paid", "0", "no"):
        return False
    return None


def merge_course(existing, incoming):
    """Two sightings of one course, combined.

    Called when the same canonical URL is returned by two queries, which is
    normal: "SAP" and "SAP ABAP" both surface the S/4HANA specialization. The
    course is one row carrying both queries, never two rows.

    Retrieval provenance accumulates. Everything else prefers the incoming
    value only when it is actually better -- a later sighting with an empty
    description must not erase a description the first sighting had.
    """
    merged = dict(existing)
    merged["discovered_via"] = sorted(
        set(existing.get("discovered_via") or ())
        | set(incoming.get("discovered_via") or ()))

    # Inactive wins: if any sighting says the material is retired, it is.
    if not incoming.get("is_active", True):
        merged["is_active"] = False

    for field in ("title", "description", "type"):
        if len(str(incoming.get(field) or "")) > len(str(existing.get(field) or "")):
            merged[field] = incoming[field]

    # A stated price beats an unknown one, whichever sighting stated it.
    if existing.get("is_free") is None and incoming.get("is_free") is not None:
        merged["is_free"] = incoming["is_free"]

    return merged
