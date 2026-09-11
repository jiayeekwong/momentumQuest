# Post-release technical debt

Work deliberately deferred past v1.0.0, with the reason it was deferred rather
than done. Each entry names what is missing and what currently stands in for
it, so a later reader can judge the risk instead of rediscovering it.

## Automated frontend interaction tests

**Missing.** There is no JavaScript test runner in this project — `frontend`
carries `eslint` and `typescript` and nothing else. The Resources page was
rewritten for v1.0.0-rc2 to filter and page on the server, and that behaviour
has no automated coverage.

Specifically untested:

- platform filtering issues a server request rather than filtering in memory
- search issues a server request, debounced ~350ms
- a superseded search response cannot overwrite a newer one (AbortController)
- changing platform or search resets the page number to 1
- only the current page's cards are rendered
- Previous / Next change the requested page

**Deferred because** adding Jest, Vitest, Playwright or Cypress to cover one
page is a toolchain decision with its own configuration, CI and maintenance
cost, and taking it during a release freeze would put untested infrastructure
into the release it was meant to protect.

**What stands in for it now:** the backend contract is covered by 17 tests in
`resources.tests.ResourceCataloguePaginationTests` — pagination default, the
page-size ceiling, platform/search/skill filters under pagination, combined
filters, and invalid page handling — plus two tests asserting the other list
endpoints still return bare arrays. The client behaviour was verified by
inspection and by a manual browser pass. That is weaker than a test: it does not
re-run, so a later refactor can silently restore the full-catalogue fetch.

**Suggested first step:** Vitest with Testing Library, mocking `fetch`, asserting
the request URLs rather than the rendered markup. The six behaviours above are
all observable from the URLs the component asks for.

## Single-source market data, and no scheduler in production

The scraper reads one source (JobStreet ICT). `ScrapeLog` records
`pages_attempted`, `blocked_count`, `status` and `error_message` because a run
can be partially blocked while the process still exits 0 — so a deployment must
read the log row, not the exit status.

Automatic scraping is deferred for the first production release by decision, and
`schedule_scraper_monthly.bat` is Windows-specific and deliberately not
deployed. Production market data therefore depends on someone running the
scraper manually until a platform-appropriate schedule exists.

## The `created` counter in `map_catalogue_to_skills`

Reported 45 creations on a pass where the table grew by 60. The resulting rows
were previewed and manually validated and a second pass was idempotent, so the
stored data is correct; the counter is not reliable for reporting. Cause not
established. Nothing was changed in the data to make it reconcile.
