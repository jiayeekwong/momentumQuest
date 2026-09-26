# Deployment runbook

                        INTERNET
                           │
                  ┌────────▼────────┐
                  │ Vercel          │  Next.js frontend
                  └────────┬────────┘
                           │ HTTPS
                  ┌────────▼────────┐
                  │ Render Free     │  Django REST API only
                  └───┬─────────┬───┘
                      │         │
              SQL/TLS │         │ S3 API
                      ▼         ▼
            ┌─────────────┐  ┌──────────────┐
            │ Neon        │  │ Cloudflare   │
            │ PostgreSQL  │  │ R2 (private) │
            └──────▲──────┘  └──────────────┘
                   │
          ┌────────┴─────────┐
          │ GitHub Actions   │  Selenium scraper
          └────────┬─────────┘
                   │ fallback
                   ▼
             Local workstation

Declared in [`render.yaml`](../render.yaml), built by
[`backend/Dockerfile`](../backend/Dockerfile), refreshed by
[`.github/workflows/refresh-market-data.yml`](../.github/workflows/refresh-market-data.yml).

Four hosts rather than one, and each split exists because a free web instance
cannot honestly do the job:

| Moved | Why |
|---|---|
| Database → Neon | nothing to bootstrap on the web host, and it survives the instance |
| Documents → R2 | free instance storage is ephemeral; a certificate on it is lost at the next deploy |
| Scraper → GitHub Actions | headless Chromium needs 400–500 MB on top of Django |
| Mail → HTTPS API | outbound SMTP is commonly blocked, and it fails silently |

---

## The three operations, kept apart

This is the distinction the rest of the document turns on.

| | When | What |
|---|---|---|
| **Bootstrap** | once per database | migrate, cache table, seed imports |
| **Deploy** | every release | build image, restart web process. Nothing else |
| **Refresh** | monthly | `refresh_market_data` |

Seed imports are **not** startup steps, and the container deliberately starts
`gunicorn` and nothing else. A web process that imported seeds would repeat the
work on every restart, on every scaled instance, and concurrently during a
rolling deploy.

---

## 1. First deployment

### 1.1 Neon

Create a project in the region nearest the Render service (Singapore — Render has
no Malaysia region). The bootstrapped database is about **27 MB**, so free-tier
storage is not a constraint.

Take the **pooled** connection details. Map them onto the variables
`config/settings.py` already reads — do not invent new names:

    DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

`DB_SSLMODE` defaults to `require` whenever `DEBUG` is false, so TLS needs no
setting. Locally it defaults to libpq's own behaviour, so a development clone
against a local server is unaffected.

### 1.2 Cloudflare R2

Create a bucket and **keep it private** — no public access, no custom public
domain. Nothing is ever served by an object URL: `CertificateFileView` streams
the bytes back through Django after checking ownership, so there is exactly one
rule and no second route to the file.

Create an API token scoped to that bucket, then set:

    R2_BUCKET, R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY

R2 is checked when a document is **first stored or read**, not when the service
starts. If these values are missing or wrong, that document operation fails;
production never falls back to the instance's temporary disk. So a successful
deploy and a passing health check say nothing about R2 — see §4, and the
document lifecycle in §7.

### 1.3 Bootstrap the database, from your own machine

Not from a Render shell: the free plan may not give you one, and the bootstrap
must not depend on the web host being reachable.

Point a local checkout at Neon and run:

    python manage.py migrate --noinput
    python manage.py createcachetable
    python manage.py import_skills
    python manage.py load_market_roles
    python manage.py import_resources

`load_market_roles` is **mandatory and the easiest step to miss**. The other
three succeed without it and leave `MarketRole` at 0, which silently empties
career-area scoping on the skill-gap page — no error, just a page that looks
thin. It is a separate command because `data/market_roles.csv` is a separately
reviewed seed.

`createcachetable` is needed because the cache *is* the database. Throttle
history lives there, and with a per-process cache the real limit on login and
password reset becomes the configured rate times the worker count. Idempotent —
safe to re-run on every deploy if you prefer.

Verify, exactly:

| | |
|---|---|
| MarketRole | 32 |
| MarketRoleAlias | 235 |
| CourseCatalogue | 5,794 |
| LearningResource | 20,434 |
| RejectedResourceMapping | 11 |

Then confirm the database matches the committed seeds:

    python manage.py export_skills --check
    python manage.py load_market_roles --check
    python manage.py export_resources --check

All three must report a match. They compare a deterministic sorted digest, not row
counts. **Do not continue if either disagrees** — a database that cannot
reproduce its own seeds is not reproducible anywhere else either.

### 1.4 Render

Create from `render.yaml`. It declares one web service: Docker build, Singapore,
free plan, no database, no disk.

Set what Render cannot infer — everything marked `sync: false`:

    DJANGO_ALLOWED_HOSTS=<service>.onrender.com
    CORS_ALLOWED_ORIGINS=https://<vercel-production-host>
    CSRF_TRUSTED_ORIGINS=https://<vercel-production-host>
    FRONTEND_URL=https://<vercel-production-host>
    DB_* (from Neon)
    R2_* (from Cloudflare)
    EMAIL_BACKEND=config.email.ResendEmailBackend
    EMAIL_API_KEY, DEFAULT_FROM_EMAIL, PRIVACY_CONTACT_EMAIL

`DJANGO_SECRET_KEY` is generated by Render. `DJANGO_DEBUG=false` and
`DJANGO_BEHIND_TLS_PROXY=true` are declared in the file.

The Vercel URL does not exist yet, so set the three origin variables to a
placeholder and correct them in §6. Nothing before then makes a cross-origin
request.

Three settings name the frontend and they answer different questions:
`CORS_ALLOWED_ORIGINS` decides who may *read* an API response,
`CSRF_TRUSTED_ORIGINS` decides whose *unsafe requests* are believed, and
`FRONTEND_URL` is what verification and password-reset emails link to. A wrong
`FRONTEND_URL` sends students to a dead link and nothing else notices.

**Do not** put `*.vercel.app` in either origin list. Every preview deployment
gets its own subdomain, so the pattern would let any preview build — including
one from a fork — make credentialed calls against production data.

If `/admin/login/` redirects forever, check `DJANGO_BEHIND_TLS_PROXY=true` took
effect *before* touching `DJANGO_SECURE_SSL_REDIRECT`. Render terminates TLS at
its edge and forwards `X-Forwarded-Proto`; without that header Django sees plain
HTTP, loops the redirect, and never sends the secure cookies.

### 1.5 Market data

There is **no** `JobListing` seed, deliberately: adverts are real market
observations with real employer names, and a committed snapshot would be stale
the day it landed. A freshly bootstrapped database has no adverts, and until it
has some, market demand and skill gap render structurally valid and completely
empty.

So run one refresh before launch — §5.

### 1.6 Frontend — §6.

---

## 2. Normal redeployment

Push to the tracked branch; Render rebuilds and restarts.

Run `migrate` when a release adds migrations. **Do not** re-run the seed imports
routinely — they are idempotent, but running them every deploy hides the case
where a release genuinely changed a seed. When one does change, run that import
and its `--check`.

---

## 3. Rollback

Re-deploy the previous image from Render's deploy history, or the previous
release tag. Tags are immutable.

Migrations do not roll back on their own. Every data migration here is
reversible, so where a rollback crosses one, reverse it explicitly:

    python manage.py migrate <app> <previous_migration>

Seeds need no rollback: the CSVs are the source of truth and the database is
derived, so re-running the matching import restores the older state.

**Backups.** Neon keeps its own history — check the retention on your plan and
do not assume it is long. For anything irreversible, take a dump first:

    pg_dump "$NEON_URL" -Fc -f momentumquest-$(date +%F).dump

R2 has no undo. Deleting a certificate object is permanent, which is why
`purge_orphaned_documents` defaults to reporting and needs `--delete`.

---

## 4. Private documents

Certificates carry students' full names and identification numbers.

    upload → Django validates → private R2 object → DB stores the key
    view   → Django checks ownership → streams the object back

The database holds an **object key**, never a URL. Reads are streamed through
`CertificateFileView`, not redirected to a signed URL: a signed URL is a second
route to the bytes, valid until its expiry regardless of what happens to the
permission that granted it, and it lands in browser history and referrer
headers.

Transcripts are different and worth knowing: they are stored, read once for text
extraction, and deleted within the same request. Nothing retains them.

**The guard.** Production names its storage backend —
`PRIVATE_STORAGE_BACKEND=r2` in `render.yaml` — and never falls back to the
instance's local filesystem. Without that, an upload to a free instance would
succeed, the row would be written, the student would be told it worked — and the
file would be gone at the next deploy, months later, with nothing in any log.

The check happens when storage is **first used**, not at startup: the backend is
resolved on the first document operation. So:

- a **missing** R2 value makes that operation fail with `ImproperlyConfigured`;
- a **present but wrong** value — a bad key, endpoint or bucket name — makes
  uploads fail, and makes an existing certificate read as missing (404) rather
  than raising an error;
- in neither case is anything written to local disk.

The consequence to plan around: **a successful deploy and a passing health check
do not prove R2 works.** Only a real certificate upload and download does, which
is why the document lifecycle in §7 is part of the smoke test rather than an
optional extra. If a certificate unexpectedly reads as missing, check the R2
credentials before assuming the object is gone.

Override with `PRIVATE_STORAGE_BACKEND=filesystem` only where local storage
genuinely persists.

---

## 5. Market refresh

Monthly, and **manual for now** (§8).

**From GitHub Actions** — Actions → *Refresh market data* → *Run workflow*.
Credentials come from repository secrets: `DB_*` and `DJANGO_SECRET_KEY`.

**From a workstation** — same command, pointed at Neon:

    python manage.py refresh_market_data --max-pages 40 --max-jobs 32

`refresh_market_data` is what makes this safe to automate later. It refuses to
run alongside another refresh, runs the acquisition, then **judges it by the
persisted `ScrapeLog` row rather than by the inner command's exit status** — and
stops before any downstream stage if the acquisition failed or was entirely
blocked. Re-extraction and classification over an unchanged table succeed
perfectly well, which is exactly what would make a stale refresh look healthy.

### A long crawl can be stopped and resumed

A full traversal takes around four hours, so it is built to survive being
interrupted. Each page's adverts are written to the database as that page
finishes, not held until the end — an interrupt, a dead browser or a dropped
connection costs the page in flight, not the run.

Stopping it with Ctrl+C closes the `ScrapeLog` row honestly (`stop_reason =
INTERRUPTED`, distinct from `FAILED` because nothing went wrong) and the summary
names the page to pick up from:

    Pagination:
        Pages attempted      : 47
        Pages with results   : 47
        Pagination exhausted : NO
        Stop reason          : INTERRUPTED
        Resume with          : --start-page 48

Then continue, passing the same ceiling — `--max-pages` is a page number, not a
count, so it means the same thing in both runs:

    python manage.py refresh_market_data --max-pages 200 --max-jobs 50       --start-page 48 --ignore-abandoned-run

`--ignore-abandoned-run` is needed on any resume started within six hours of the
run it continues: that run's row is, correctly, still unfinished.

A resumed run can still reach `PAGINATION_EXHAUSTED`. Coverage is a property of
where the crawl stopped, not of how many sittings it took.

### A finished scrape is not a complete one

`--max-pages` is a safety ceiling, not an expected page count. A run that stops
because it hit the ceiling has covered an unknown fraction of the search, and it
reports SUCCESS while doing so — which is why coverage is reported separately:

    Pagination status: EXHAUSTED

means the crawl reached the last page JobStreet offered, and only then was the
configured search traversed end to end. Anything else prints

    Pagination status: INCOMPLETE (MAX_PAGES_REACHED)

with the reason, and the same pair is on the `ScrapeLog` row as `stop_reason` and
`pagination_exhausted`. `BLOCKED` and `FAILED` are never read as completion: an
empty page only ends pagination once it has been confirmed to have loaded as a
JobStreet results page, because a bot wall, an error page and a markup change all
arrive looking like a search with no matches.

To prove a full traversal, raise the ceiling until the run stops on its own:

    python manage.py refresh_market_data --max-pages 200

and read the stop reason rather than the page count. Note that `--max-jobs` caps
adverts *per page*, so a run can exhaust pagination and still have skipped
adverts; the summary says so when it happens.

### A crawl outlives its database connection

The crawl runs for hours and makes no query while it does, so the command holds
no connection across it — it closes one before the crawl and opens a new one
after. Anything else is dropped by a hosted database or by whatever sits between
you and it, and the first write afterwards fails with `server closed the
connection unexpectedly`, taking the whole crawl with it.

That is also why a second refresh is refused by the unfinished `ScrapeLog` row
rather than by the advisory lock the command still takes at startup. An advisory
lock lives on the connection holding it, so it would be released by the very
drop it was meant to survive. The row is data, and outlasts the session.

A refresh killed mid-crawl therefore leaves an unfinished row behind, and the
next run refuses for six hours in case that run is still going. When it is known
to be dead:

    python manage.py refresh_market_data --max-pages 40 --max-jobs 32       --ignore-abandoned-run

On success it runs, in dependency order: `dedupe_scraped_listings`,
`recategorize_job_listings`, `reextract_job_skills`, `classify_market_roles`,
`refresh_skill_gaps`.

### Never trust the exit code of `scrape_jobs` itself

Run directly, it exits 0 whether it worked or not. A validation run recorded

    Status  : FAILED
    Error   : Could not reach host. Are you offline?

and still exited 0. `refresh_market_data` exists to convert that into a non-zero
exit. If you ever run the bare scraper, read the row:

    python manage.py shell -c "from job_listings.models import ScrapeLog; \
      r=ScrapeLog.objects.latest('id'); \
      print(r.status, r.pages_attempted, r.jobs_scraped, r.blocked_count, r.error_message)"

Verify after a refresh:

    JobListing > 0        JobSkill > 0
    classified adverts > 0
    market-demand.total_postings > 0
    skill-gap.total_listings > 0   (for a student with a target role)

### If the source blocks the runner

`my.jobstreet.com` answered **403** to a plain request during validation, and
cloud IP ranges are commonly bot-blocked. Selenium from a residential connection
succeeded — which says nothing about a GitHub runner.

If hosted runs are blocked: record it, leave the failure in `ScrapeLog`, and keep
the refresh on a workstation. Do **not** add stealth or bypass techniques, do not
mark the run successful, and do not populate the database by hand. A blocked
runner is a hosting-compatibility finding with a legitimate answer already in
place — the workstation fallback.

---

## 6. Frontend (Vercel)

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Framework | Next.js |
| Environment variable | `NEXT_PUBLIC_API_URL=https://<render-api>.onrender.com` |

`NEXT_PUBLIC_*` is **inlined at build time**, not read at runtime. It must exist
in the Vercel project *before* the build, and changing it requires a rebuild —
setting it afterwards changes nothing in an already-built bundle.

Then set `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` and `FRONTEND_URL` on
Render to the stable Vercel production origin, and restart.

Confirm in DevTools that API traffic goes to the Render HTTPS domain — not
`localhost:8000` — with no CORS or CSRF errors.

---

## 7. Smoke-test checklist

Against the deployed stack, with real advert data present:

- [ ] `check --deploy` reports no issues
- [ ] `/admin/login/` returns 200 **and is styled** (WhiteNoise serving static)
- [ ] protected endpoints return 401 without a token
- [ ] registration enforces the privacy and document-consent gates
- [ ] a verification email actually arrives (the HTTPS backend is working)
- [ ] login issues a JWT; `/api/auth/profile/` accepts it
- [ ] `market-demand.total_postings > 0`
- [ ] `skill-gap.total_listings > 0` for a student with a target role
- [ ] skill gap lists missing skills with related courses per skill
- [ ] Resources: default request returns ~24 rows and tens of KB, **not** the
      whole catalogue
- [ ] Resources platform filter, search and skill filter each issue a server
      request; Previous / Next change the page
- [ ] `ScrapeLog.status` is SUCCESS for the launch refresh

### The document lifecycle, end to end

Use a **purpose-made test student and a document created for it**. Never a real
student's development certificate: the production bucket starts empty by design,
and copying someone's identity-bearing document across to make a test convenient
is a disclosure with no upside.

- [ ] upload a certificate as the test student — succeeds
- [ ] the object exists in R2, and the bucket is private (a direct object URL is
      refused; only Django serves it)
- [ ] the owning student can open it
- [ ] an admin can open it, and a `CERTIFICATE_VIEWED_BY_ADMIN` privacy event is
      recorded
- [ ] a *different* student gets 403, not the file
- [ ] the certificate still opens **after a redeploy** — the point of R2, and the
      thing a filesystem would have failed
- [ ] no temporary copy is left behind (transcript upload is the path that makes
      one; it is removed when the request ends)
- [ ] deleting the certificate removes the R2 object
- [ ] `purge_orphaned_documents` reports orphans and removes nothing without
      `--delete`

Then remove the test student and confirm their document went with them.

---

## 8. Deferred: automatic monthly scraping

The workflow has `workflow_dispatch` only. Two things must be true before a
`schedule:` is added:

1. **Trust.** `refresh_market_data` now exits non-zero on a failed acquisition,
   which is the prerequisite. It needs a few real hosted runs behind it.
2. **Reachability.** Whether a GitHub runner can reach the job board at all is
   unestablished (above).

`backend/schedule_scraper_monthly.bat` is the Windows workstation equivalent and
is not deployed anywhere.

Still wanted before unattended scheduling:

- staleness monitoring, so "no successful refresh in N days" alerts rather than
  being noticed by a student looking at a thin page.

**Do not** add keep-alive traffic to stop the free web instance sleeping. See
[free-tier operations](free-tier-operations.md) for what the limits actually are
and how the application handles them.
