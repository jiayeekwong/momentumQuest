"""One shape for every course provider, and one place skills are decided.

The rule this package exists to enforce: a provider knows how to *find*
courses and nothing else. What a course teaches is settled afterwards, by the
canonical skill extractor, from the course's own words. No adapter matches
skills, and none may -- per-provider matching is how a catalogue ends up with
Coursera courses judged by one rule and SAP courses by another, and with
nobody able to say why a student was recommended something.

That separation already paid once. The Coursera scraper carried its own copy
of the boundary matcher, and the copy still had the bug the extractor had been
fixed for: "C#" and "C++" matched nothing, while ".NET" matched inside
"ASP.NET Core". The fix was to delete the copy, not to repair it.

A provider therefore returns evidence, not conclusions:

    url            canonical, the provider's stable identity for the course
    title          what it is called
    description    the provider's own words -- a skills-gained list, a summary
    provider       who published it
    type           Course, Specialization, Certification, Learning Path ...
    is_free        True, False, or None where the provider does not say
    discovered_via the query that surfaced it, as retrieval provenance

``discovered_via`` is never evidence of meaning. A search for "Root Cause
Analysis" surfacing a Six Sigma course says something about the search, not
about the course.
"""

import abc


class CourseProvider(abc.ABC):
    """A source of courses that can be searched by phrase.

    Subclasses implement :meth:`search` and declare :attr:`name`. Everything
    else -- deduplication, storage, skill mapping, seeding -- is shared, so a
    new provider is a search method and nothing more.
    """

    #: Stored on every row this provider contributes, and the value students
    #: see. Stable: changing it orphans previously stored rows.
    name = None

    #: Whether this provider is the vendor for the technology it teaches.
    #: Used only to prefer between resources that already map to a skill on
    #: their own evidence -- never to create a mapping. Microsoft Learn is the
    #: vendor for .NET; that is a reason to rank its .NET course first, and
    #: never a reason to call one of its courses a .NET course.
    is_vendor = False

    #: Vendor authority is per-technology, not global. Microsoft Learn is
    #: authoritative for C#, not for SAP. Names are canonical skill names.
    vendor_for = ()

    def __init__(self, driver_factory=None):
        #: Providers that need a browser take one lazily, so an API-backed
        #: provider never starts Chrome.
        self._driver_factory = driver_factory

    @abc.abstractmethod
    def search(self, phrase):
        """Courses matching one search phrase.

        Returns an iterable of dicts carrying the fields named in this
        module's docstring. Raising is acceptable and expected: the
        acquisition runner classifies the failure, rebuilds a session if the
        provider needs one, and retries.
        """

    # ------------------------------------------------------------------

    def canonical_url(self, href):
        """This provider's stable identity for a course.

        Defaults to stripping query strings and fragments, which is what makes
        a tracking-parameter variant and a bare link one row rather than two.
        Providers whose identity is not the path override this.
        """
        return href.split("?")[0].split("#")[0].rstrip("/")

    def search_terms(self, skill_name, phrase):
        """The strings to actually search for, in order of preference.

        Retrieval is provider-specific, and the normalised phrase is not always
        the better query. It is tuned for a fuzzy search engine: Coursera finds
        chemistry for "RCA" and the right courses for "Root Cause Analysis". A
        catalogue API matching substrings behaves the opposite way -- "C#
        programming" occurs nowhere in Microsoft Learn's 4,488 titles while
        "C#" occurs in 66 -- so the expansion silently cost recall on the very
        skills that provider is best for.

        Default is the phrase alone, which is what a search engine wants.
        Providers that match literally override this.
        """
        return [phrase]

    def reset(self):
        """Drop any session this provider holds. Called on failure and at exit.

        A no-op for an API-backed provider, which is the point: the browser
        machinery the Coursera acquisition needs must not be a tax on a
        provider that only makes an HTTPS request.
        """

    # Deliberately no `prefers(skill)` here. Asking a provider whether it is
    # authoritative invites the provider-level answer this design rejects --
    # "Microsoft Learn is authoritative" is false as stated. The question is
    # about a Skill x Provider pair and is answered in providers.authority,
    # which also detects two providers claiming one skill.


#: Adapters register here so the runner can be told a provider by name.
_REGISTRY = {}


def register(provider_class):
    _REGISTRY[provider_class.name] = provider_class
    return provider_class


def get_provider(name, **kwargs):
    """An adapter, but only for a provider we are permitted to acquire from.

    The check lives here rather than in each command so it cannot be forgotten
    by a new caller. A registered adapter for a BLOCKED provider still cannot
    run -- registration is a capability, permission is a separate question, and
    conflating them is how a policy decision gets undone by a later refactor.
    """
    from .policy import is_permitted, status_for

    if name not in _REGISTRY:
        raise KeyError(f"Unknown provider: {name!r}. Known: {sorted(_REGISTRY)}")
    if not is_permitted(name):
        raise PermissionError(
            f"Acquisition from {name!r} is {status_for(name)}. See "
            f"resources.providers.policy for the evidence and the route to "
            f"changing it.")
    return _REGISTRY[name](**kwargs)


def provider_names():
    return sorted(_REGISTRY)
