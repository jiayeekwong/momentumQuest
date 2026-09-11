# Deployment runbook

    Vercel (Next.js)  ──HTTPS──▶  Render web service  ──▶  PostgreSQL
                                         │
                                         └──▶  disk at /var/data (private media)

Topology is declared in [`render.yaml`](../render.yaml); the backend image is
[`backend/Dockerfile`](../backend/Dockerfile).

The distinction this document exists to make:

| | |
|---|---|
| **Every deploy** | build the image, run the web process. Nothing else. |
| **First bootstrap only** | migrations, cache table, seed imports. Once, per database. |

Seed imports are **not** startup steps. A web process that ran them would re-run
them on every restart, on every scaled instance, and concurrently during a
rolling deploy. The container deliberately starts `gunicorn` and nothing else.

---

## 1. First deployment

### 1.1 Create the services

Point Render at the repository; `render.yaml` defines the web service, the
PostgreSQL database and the private-media disk. The database and the web service
must share a region (`singapore` as declared — closest to the market this
serves).

### 1.2 Set the environment variables Render cannot infer

Everything marked `sync: false` in `render.yaml`. Use these exact names — they
are what `config/settings.py` reads:

    DJANGO_DEBUG=false                                  (declared)
    DJANGO_SECRET_KEY                                   (Render generates)
    DJANGO_BEHIND_TLS_PROXY=true                        (declared)
    DJANGO_ALLOWED_HOSTS=<render-api-host>
    CORS_ALLOWED_ORIGINS=https://<vercel-production-host>
    CSRF_TRUSTED_ORIGINS=https://<vercel-production-host>
    FRONTEND_URL=https://<vercel-production-host>
    DJANGO_PRIVATE_MEDIA_ROOT=/var/data/private_media   (declared)
    DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT (from the database)
    EMAIL_HOST / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD / DEFAULT_FROM_EMAIL
    PRIVACY_CONTACT_EMAIL

Three separate settings name the frontend and they are not interchangeable:
`CORS_ALLOWED_ORIGINS` decides who may read an API response,
`CSRF_TRUSTED_ORIGINS` decides whose unsafe requests are believed, and
`FRONTEND_URL` is what verification and password-reset emails link to. A wrong
`FRONTEND_URL` sends students to a dead link and nothing else notices.

`CSRF_TRUSTED_ORIGINS` defaults to the CORS list, so it only needs setting when
the admin is reached on a different host. Entries need the scheme.

### 1.3 Bootstrap the database — once

From a Render shell on the web service:

    python manage.py migrate --noinput
    python manage.py createcachetable
    python manage.py import_skills
    python manage.py load_market_roles
    python manage.py import_resources
    python manage.py collectstatic --noinput
    python manage.py check --deploy

`load_market_roles` is **mandatory and easy to miss**. `migrate`,
`import_skills` and `import_resources` all succeed without it and leave
`MarketRole` at 0, which silently empties career-area scoping on the skill-gap
page. It is a separate command because `data/market_roles.csv` is a separately
reviewed seed.

`createcachetable` is needed because the cache is the database (see
`DJANGO_CACHE_URL` in `backend/.env.example`). Throttle history lives there, and
a per-process cache would make the real login rate limit the configured rate
times the worker count. It is idempotent — safe to re-run.

Verify the bootstrap, exactly:

| | |
|---|---|
| MarketRole | 31 |
| MarketRoleAlias | 228 |
| CourseCatalogue | 5,794 |
| LearningResource | 20,434 |
| RejectedResourceMapping | 11 |

Then confirm the database matches the committed seeds:

    python manage.py export_skills --check
    python manage.py export_resources --check

Both must report a match. They compare a deterministic sorted digest, not row
counts.

`check --deploy` should report no issues. If it flags `security.W008`
(`SECURE_SSL_REDIRECT`), check `DJANGO_BEHIND_TLS_PROXY=true` is set before
disabling the redirect — Render terminates TLS at its edge and forwards
`X-Forwarded-Proto`, and without that header Django sees plain HTTP, loops the
redirect and never sends the secure cookies. `DJANGO_SECURE_SSL_REDIRECT=false`
is the fallback only if Render's health check cannot follow the redirect;
Render already forces HTTPS at the edge.

### 1.4 Acquire market data — before launch, not after

There is **no** `JobListing` seed, deliberately: adverts are real market
observations with real employer names, and a committed snapshot would be stale
the day it landed. A freshly bootstrapped database therefore has **no adverts**,
and until it has some, market demand and skill gap render structurally valid and
completely empty.

So run the scraper once, manually, against the production database — see §4.

### 1.5 Deploy the frontend

See §6.

---

## 2. Normal redeployment

Push to the tracked branch. Render rebuilds the image and restarts the web
process.

Run `migrate` when a release adds migrations. **Do not** re-run `import_skills`,
`load_market_roles` or `import_resources` as routine steps — they are
idempotent, but they are bootstrap operations, and running them on every deploy
hides the case where a release genuinely changed a seed.

When a release *does* change a seed file, run that one import and then its
`--check`.

---

## 3. Private media

Certificates and transcripts carry students' full names and identification
numbers. They are stored outside `MEDIA_ROOT` and served only through an
ownership-checked view, because everything under `MEDIA_ROOT` is served without
authentication.

The container filesystem is ephemeral. `render.yaml` mounts a disk at
`/var/data`, and `DJANGO_PRIVATE_MEDIA_ROOT=/var/data/private_media` puts the
files on it. **Without the disk, every deploy silently discards every uploaded
certificate.** Confirm the mount exists before accepting any upload in
production.

---

## 4. Manual market refresh

Automatic monthly scraping is **deferred** — see §8.

    python manage.py scrape_jobs --max-pages <n> --max-jobs <n>
    python manage.py classify_market_roles

### The exit code is not the result

`scrape_jobs` exits 0 whether it worked or not. Observed during release
validation: a run printed

    Status  : FAILED
    Error   : Could not reach host. Are you offline?

and exited 0. Read the persisted `ScrapeLog` row, never `$?`:

    python manage.py shell -c "from job_listings.models import ScrapeLog; \
      r=ScrapeLog.objects.latest('id'); \
      print(r.status, r.pages_attempted, r.jobs_scraped, r.blocked_count, r.error_message)"

Record: final status, pages attempted, jobs acquired, `blocked_count`, error
message, and the latest successful `finished_at`.

Then verify the data actually landed:

    JobListing  > 0
    JobSkill    > 0
    classified adverts > 0        (JobListing.market_role is not null)
    market-demand.total_postings  > 0
    skill-gap.total_listings      > 0   (for a student with a target role)

### If JobStreet is blocked from Render

`my.jobstreet.com` answered **403** to a plain request during validation, and
cloud provider IP ranges are commonly bot-blocked. Selenium with real Chromium
succeeded from a residential connection, but that is not evidence about Render.

If the hosted run is blocked: record it, leave the failure in `ScrapeLog`, and
treat it as a hosting-compatibility finding. Do **not** add stealth or bypass
techniques, do not mark the run successful, and do not populate the launch
database by hand. A scrape that cannot run from Render is a deployment problem
with legitimate answers — running the refresh from elsewhere against the same
database, or a different acquisition source — not a scraper to be disguised.

---

## 5. Rollback

Re-deploy the previous image from Render's deploy history, or the previous
release tag. Tags are immutable: `v1.0.0-rc1`, `v1.0.0-rc2`, `v1.0.0-rc3`.

Migrations do not roll back automatically. Every data migration in this project
is reversible, so where a rollback crosses one, reverse it explicitly:

    python manage.py migrate <app> <previous_migration>

Seed data needs no rollback step — the CSVs are the source of truth and the
database is derived from them, so re-running the matching import restores the
older state.

---

## 6. Frontend (Vercel)

| Setting | Value |
|---|---|
| Root Directory | `frontend` |
| Framework | Next.js |
| Environment variable | `NEXT_PUBLIC_API_URL=https://<render-api-domain>` |

`NEXT_PUBLIC_*` is **inlined at build time**, not read at runtime. The variable
must exist in the Vercel project *before* the build, and changing it requires a
rebuild — setting it afterwards changes nothing in an already-built bundle.

Do not commit a production URL to `.env.local`. `frontend/.env.example` carries
the local default and documents the override.

After deploying, confirm in the browser that requests go to the Render domain
and not to `localhost:8000`.

---

## 7. Smoke-test checklist

Against the deployed stack, with real advert data present:

- [ ] `check --deploy` reports no issues
- [ ] `/admin/login/` returns 200 **and is styled** (WhiteNoise serving static)
- [ ] protected endpoints return 401 without a token
- [ ] registration enforces the privacy and document-consent gates
- [ ] login issues a JWT; `/api/auth/profile/` accepts it
- [ ] `market-demand.total_postings > 0`
- [ ] `skill-gap.total_listings > 0` for a student with a target role
- [ ] skill gap lists missing skills with related courses per skill
- [ ] Resources page: default request returns ~24 rows, tens of KB — **not** the
      whole catalogue
- [ ] Resources platform filter, search and skill filter each issue a server
      request
- [ ] Previous / Next change the page
- [ ] a certificate upload survives a redeploy (private disk mounted)
- [ ] `ScrapeLog.status` is SUCCESS for the launch scrape

---

## 8. Deferred: monthly Cron

Not defined in `render.yaml`, on purpose. `scrape_jobs` exits 0 on failure, so as
an unattended monthly job it would report success while market data silently went
stale — and stale market data is not a visible outage, it is a skill gap quietly
computed against last year's adverts.

`backend/schedule_scraper_monthly.bat` is Windows-specific and is not deployed.

Before enabling a schedule, a production-safe orchestration command needs:

- an advisory or database lock, so an overrunning run and the next scheduled one
  cannot interleave writes;
- fail-fast execution and a **non-zero exit** on failure, so platform alerting
  means something;
- durable per-run metrics — `ScrapeLog` already carries status,
  `pages_attempted`, `blocked_count`, `error_message`;
- a staleness check, so "no successful scrape in N days" alerts rather than being
  noticed by a student.

Until then: manual refresh per §4, run and verified by a person.
