"""Whether we are permitted to acquire from a provider, and on what evidence.

Checked before an adapter is written, not after. An adapter is the expensive
part and the policy is the cheap part, so discovering that a site forbids
automated access *after* building a scraper for it wastes the work and leaves a
tempting, already-written way to ignore the answer.

Each entry records what was checked, when, and what it said. A status here is a
finding with a citation, never an assumption: "probably fine" is not a status,
and an unchecked provider stays PENDING until somebody fetches its robots.txt
and reads its terms.

STATUSES
    ALLOWED   robots.txt permits the paths we would fetch, or the provider
              publishes an API intended for this use.
    BLOCKED   the provider disallows it. No adapter, and no browser-driven
              workaround -- driving Chrome at a disallowed path is the same
              request with a different user agent.
    NO_PUBLIC_INTERFACE
              permitted, but nothing public to read: a single-page app whose
              catalogue arrives over an undocumented internal call, or a
              login-gated platform. An adapter would mean driving a browser to
              scrape an application, which is fragile in a way this project has
              already paid for once, and is a poor trade when the same effort
              buys a whole catalogue from an API-backed provider.
    PENDING   not yet checked.
"""

ALLOWED = "ALLOWED"
BLOCKED = "BLOCKED"
PENDING = "PENDING"
#: Permitted, but there is nothing to acquire from. A distinct answer from
#: BLOCKED, and worth distinguishing: BLOCKED is the site's decision and will
#: not change on its own, while this is an observation about the site's
#: architecture that a published API would overturn tomorrow.
NO_PUBLIC_INTERFACE = "NO_PUBLIC_INTERFACE"

ACQUISITION_POLICY = {
    "Coursera": {
        "status": ALLOWED,
        "checked": "2026-09-07",
        "evidence": (
            "robots.txt permits /search for general user-agents. Search "
            "results are the only path fetched; course pages are not crawled."
        ),
        "route": "Public search pages, rendered with a browser.",
    },
    "Microsoft Learn": {
        "status": ALLOWED,
        "checked": "2026-09-07",
        "evidence": (
            "learn.microsoft.com/api/catalog/ is a published catalog API "
            "returning modules, learning paths, certifications and courses. "
            "It is fetched once per run and filtered locally, so the load is "
            "one request rather than one per query."
        ),
        "route": "Published catalog API. No browser, no scraping.",
    },
    "AWS Skill Builder": {
        "status": NO_PUBLIC_INTERFACE,
        "checked": "2026-09-08",
        "evidence": (
            "robots.txt permits everything ('User-agent: * / Allow: /'), so "
            "policy is not the obstacle. The published sitemap holds 27 URLs "
            "and every one is navigation -- /getstarted, /roles, /products, "
            "/subscriptions, /login, ten /exam-prep pages -- with no course "
            "entries at all. /search?searchText=EC2 returns a 7.7KB shell "
            "mentioning EC2 zero times and linking no courses, and the HTML "
            "names no API endpoint."
        ),
        "route": (
            "None available. Revisit if AWS publishes a catalogue API; the "
            "ten /exam-prep pages are real content and were not confirmed "
            "server-rendered before connectivity dropped, so they remain the "
            "one avenue worth re-checking."
        ),
    },
    "Cisco Networking Academy": {
        "status": ALLOWED,
        "checked": "2026-09-07",
        "evidence": (
            "netacad.com/robots.txt carries no Disallow rules at all, plus a "
            "sitemap. It does set 'Crawl-delay: 10', which is a condition "
            "rather than a permission: an adapter must space requests ten "
            "seconds apart, well above this project's default politeness "
            "delay."
        ),
        "route": (
            "Sitemap enumeration honouring Crawl-delay: 10. The runner's "
            "`delay` argument exists for exactly this."
        ),
    },
    "Oracle MyLearn": {
        "status": NO_PUBLIC_INTERFACE,
        "checked": "2026-09-08",
        "evidence": (
            "education.oracle.com does not resolve; the live platform is "
            "mylearn.oracle.com, whose robots.txt is 'User-agent: *' with no "
            "Disallow -- so, again, policy is not the obstacle. Its sitemap "
            "holds 46 URLs: /home/, /digital-library/ and 44 /story/<id>/ "
            "pages, all lastmod 2022. Every path -- a story page, a learning "
            "path page, the root -- returns the identical 10,561-byte shell "
            "with the same generic <title>Oracle MyLearn</title> and og "
            "description, and no course links. Sign-in runs through "
            "login-ext.identity.oraclecloud.com, so the catalogue is behind "
            "authentication."
        ),
        "route": (
            "None available. The public surface carries no course data, and "
            "the data that exists is login-gated -- which is a different "
            "problem from rendering, and one a browser would not solve either."
        ),
    },
    "edX": {
        "status": ALLOWED,
        "checked": "2026-09-08",
        "evidence": (
            "edx.org/robots.txt disallows /search? and /es/search? (lines 58-59) "
            "and sets Crawl-delay: 10, and publishes a sitemap at "
            "/sitemap.xml. Course and catalogue pages are not disallowed."
        ),
        "route": (
            "Sitemap only. The /search? endpoint is disallowed and must not be "
            "fetched -- not by a browser either, since that is the same "
            "request with a different user agent. Requests spaced 10 seconds "
            "apart per Crawl-delay."
        ),
        #: A correction worth keeping. An earlier check of this file read only
        #: its first dozen Disallow lines and concluded search was permitted;
        #: the search rules sit at lines 58-59, past where that read stopped.
        #: A policy finding is only as good as the whole file it cites.
        "correction": (
            "Recorded ALLOWED-for-search on 2026-09-07 from a truncated read. "
            "Corrected 2026-09-08: /search? is disallowed."
        ),
    },
}


def status_for(provider_name):
    return ACQUISITION_POLICY.get(provider_name, {}).get("status", PENDING)


def is_permitted(provider_name):
    """Only an explicit ALLOWED permits acquisition.

    PENDING is not permission. An unchecked provider must not become an
    implemented one by default, which is the failure this module exists to
    prevent.
    """
    return status_for(provider_name) == ALLOWED


def blocked_providers():
    return {name: row for name, row in sorted(ACQUISITION_POLICY.items())
            if row["status"] == BLOCKED}


def pending_providers():
    return {name: row for name, row in sorted(ACQUISITION_POLICY.items())
            if row["status"] == PENDING}
