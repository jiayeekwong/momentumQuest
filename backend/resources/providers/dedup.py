"""When two course rows are the same course, and when they only look alike.

Two questions with very different answers, kept apart deliberately.

**Within one provider** the answer is mechanical. A provider has a stable
identity for each course -- its canonical URL -- and the same course arrives
under several spellings of it: with tracking parameters, with a trailing
slash, with a fragment. Those are one row. This is settled by
``CourseProvider.canonical_url`` and needs no judgement.

**Across providers** the answer is almost always "no". Coursera's "Python for
Everybody" and Microsoft Learn's "Get started with Python" are different
courses, by different authors, of different length, teaching overlapping
material. Merging them would destroy the thing a student is choosing between,
and would make the vendor preference meaningless -- there would be nothing
left to prefer.

So cross-provider merging is off by default and requires an explicit,
reviewed claim that two URLs are the same artefact. That happens: a provider
re-hosts another's course under its own domain, or one redirects to the other.
It is rare enough to enumerate and too consequential to infer from a title
similarity score, which is exactly the "merely similar" mistake.
"""

import logging

logger = logging.getLogger(__name__)

#: Reviewed cross-provider equivalences: {url: url_it_is_the_same_as}.
#:
#: Deliberately empty. An entry here is a human claim that two providers are
#: serving one artefact, and each should carry the evidence in a comment. No
#: such case has been found yet, and an inferred one would be a bug -- title
#: similarity is not identity, and 40 Coursera Python courses would collapse
#: into one.
CROSS_PROVIDER_EQUIVALENTS = {}


def group_key(course):
    """The identity a course is deduplicated on.

    Provider plus URL, so two providers can never collide by accident, and one
    provider's URL variants always collapse. A reviewed equivalence rewrites
    the key to its target, which is what makes the merge happen at all.
    """
    url = course["url"]
    canonical = CROSS_PROVIDER_EQUIVALENTS.get(url)
    if canonical is not None:
        # The equivalence names a specific URL, so the merged row takes that
        # URL's identity, provider included. Anything else would leave a row
        # whose provider and URL disagree.
        return canonical
    return f"{course['provider']}|{url}"


def deduplicate(courses, merge=None):
    """Collapse repeated sightings into one row each, preserving order.

    ``merge`` combines two sightings; the default keeps the first and is only
    useful in tests. Production passes ``normalize.merge_course``, which
    accumulates retrieval provenance rather than discarding it.
    """
    merge = merge or (lambda existing, incoming: existing)

    by_key = {}
    order = []
    for course in courses:
        key = group_key(course)
        if key in by_key:
            by_key[key] = merge(by_key[key], course)
        else:
            by_key[key] = course
            order.append(key)
    return [by_key[key] for key in order]


def cross_provider_report(courses):
    """Titles seen from more than one provider, for review -- never merged.

    This is the input a person would need to decide whether an equivalence
    belongs in CROSS_PROVIDER_EQUIVALENTS. It reports and stops there: the
    whole point is that a machine must not make this call, and a report that
    quietly merged would be the bug it exists to prevent.
    """
    by_title = {}
    for course in courses:
        key = " ".join(course["title"].split()).casefold()
        by_title.setdefault(key, []).append(course)

    return {
        title: rows for title, rows in sorted(by_title.items())
        if len({row["provider"] for row in rows}) > 1
    }
