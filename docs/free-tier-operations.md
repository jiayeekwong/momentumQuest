# Running on free tiers: what to expect

This deployment costs approximately nothing, and the limits that buys are real.
They are written down here rather than discovered during a demonstration, and
none of them is worked around by trickery.

## The API sleeps

A free Render instance is spun down after a period without traffic. The next
request wakes it, and that first request can take the better part of a minute
while the container starts, Django imports, and the first database connection is
made.

**What this looks like:** the site loads (Vercel is always warm — it is static
hosting plus edge functions), and then the first panel that needs data sits
waiting. Without care that reads as a crashed application rather than a cold
start.

**What the application does about it:** pending data renders as a placeholder
rather than as a zero. The student dashboard shows an em dash in each stat tile
and a pulsing skeleton where the demand chart will be; the skill-gap, jobs and
resources pages hold a skeleton grid while their request is in flight. The
distinction that matters during a cold start is "not yet" versus "none" — a tile
reading 0 says the student has no applications, which is a different and wrong
statement.

**What is deliberately not done:** no keep-alive pinger, no cron hitting the
health check every ten minutes, no uptime monitor configured to keep the dyno
awake. Those exist to defeat the sleeping rule rather than to observe anything,
they consume the same free allowance they are trying to preserve, and a free tier
kept permanently awake by synthetic traffic is a paid tier taken without paying.
If cold starts become unacceptable, the honest fixes are a paid instance or a
host that does not sleep.

**Worth knowing for a demonstration or viva:** open the site a minute before you
need it. The instance stays warm while it is being used.

## The database is somewhere else

Neon is a separate service reached over TLS across the public internet, which has
three consequences worth knowing.

Every query pays a network round trip that a local socket did not. `CONN_MAX_AGE`
holds connections open for ten minutes in production to avoid re-establishing TLS
per request, with `CONN_HEALTH_CHECKS` making that safe when the server has closed
one in the meantime.

Keep the Neon project in the same region as the Render service. A database in a
different continent turns every page into a series of intercontinental round
trips.

Neon's free tier may suspend an idle database, so the first query after a quiet
period can be slow for the same reason the API is — and both can happen to the
same unlucky first request.

## Private documents are in object storage, not on the host

Certificates live in a private Cloudflare R2 bucket. This is not a performance
choice: a free instance's filesystem is discarded when the container is replaced,
so a certificate written there is lost at the next deploy — silently, with the
database row still pointing at it.

Production never falls back to the instance's filesystem, because that particular
failure produces no error at the time: the upload succeeds, the student is told it
worked, and the file is simply gone weeks later. Instead the storage configuration
is checked when a document is first stored or read, and a missing or wrong R2
setting makes that operation fail rather than quietly writing somewhere temporary.

That check happens on first use, not at startup. A deploy that succeeds and a
health check that passes therefore say nothing about whether R2 works — only a
real certificate upload and download does.

R2's free allowance is generous relative to this project (a few thousand
documents of a few hundred KB each), and it charges no egress. Deletion is
permanent, which is why `purge_orphaned_documents` reports by default and removes
only with `--delete`.

## The scraper runs somewhere else again

Headless Chromium wants 400–500 MB on top of Django, which a free instance does
not have, and carrying a browser in the API image year-round for a monthly job is
poor value. The refresh runs on a GitHub Actions runner instead, writing to the
same Neon database.

**This may not work, and that is a known open question.** `my.jobstreet.com`
answered 403 to a plain request during validation; cloud provider IP ranges are
commonly bot-blocked. Selenium from a residential connection succeeded, which is
evidence about that connection and not about a runner.

So the workstation fallback is a first-class part of the design, not a
contingency: the same `refresh_market_data` command, run locally against Neon. If
hosted runs are blocked, that is recorded honestly and the refresh stays local.
Bypass techniques are not on the table.

## Mail goes over HTTPS

Outbound SMTP ports are commonly blocked on free hosting, and that failure is
quiet in the worst way: `send_mail` hangs until it times out, the registration
request still returns success, and the verification link never arrives — so the
student cannot log in and nothing explains why.

Production therefore uses a transactional-email API over HTTPS. Every caller uses
`django.core.mail.send_mail`, so the provider is a settings value and no
application code is coupled to it.

Free email tiers usually require a verified sending domain and cap daily volume.
For this project's traffic — verification and password resets — the cap is not the
constraint; the verified domain is the setup step people forget.

## Nothing here is monitored

There is no alerting. A failed market refresh is visible in the GitHub Actions
run and in the `ScrapeLog` row, and nowhere else. Stale market data is not an
outage: the pages still render, the numbers are just quietly out of date.

That is the gap worth closing first if this grows beyond a project — staleness
monitoring, so "no successful refresh in N days" alerts rather than being noticed
by a student looking at a thin page. See
[post-release technical debt](post-release-technical-debt.md).

## Summary

| | Limit | Mitigation |
|---|---|---|
| Render Free | sleeps when idle; slow first request | loading states; open early before a demo |
| Neon Free | external, may suspend when idle | same region; connection reuse |
| R2 | deletion is permanent | purge reports before it removes |
| GitHub Actions | runner may be blocked by the source | workstation fallback, same command |
| Email | verified domain required; daily cap | HTTPS API behind configuration |
| Everything | no alerting | read `ScrapeLog` after each refresh |
