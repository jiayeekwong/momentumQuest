@echo off
:: MomentumQuest - Monthly data refresh
::
:: This is the ONLY scheduled job. It runs both scrapers and every step that
:: depends on them, in the order they depend on each other.
::
:: Register with Windows Task Scheduler:
::   schtasks /create /tn "MomentumQuest Monthly Refresh" ^
::            /tr "<path-to-your-checkout>\backend\schedule_scraper_monthly.bat" ^
::            /sc monthly /d 1 /st 02:00
::
:: COVERAGE NOTE: JobStreet advertises a posting for ~30 days
:: (job_listings/expiry.py: SOURCE_LISTING_LIFESPAN_DAYS = 30), so a monthly
:: run samples that window exactly once. Adverts that open and lapse between
:: two runs are never seen at all. Monthly is the chosen cadence; --max-pages
:: is set high to compensate by going deeper on the day it does run.
::
:: A second consequence of monthly: the dashboard's month-on-month figure is
:: only computed when the scraper ran the same number of times in both months
:: (dashboard/views.py collection_effort). An irregular schedule -- three runs
:: one month, none the next -- makes the comparison measure our own cadence
:: rather than employer demand, so it is withheld and the page says why.
:: Keeping this task on a fixed monthly trigger is what makes that number
:: appear at all.
::
:: Skill gaps are NOT refreshed on a schedule of their own. They have two
:: event triggers instead:
::   * market side  - scrape_jobs re-records every student's gaps at the end
::                    of a run, but only when the scrape actually changed
::                    something.
::   * student side - resources/skill_recognition.py apply_skills refreshes
::                    one student the moment a certificate is endorsed or a
::                    transcript is read.
:: A timed refresh would either fire when nothing had changed or lag behind
:: the change that mattered.

:: Self-locating: %~dp0 is the folder holding this script, so the
:: scheduled task works from any checkout path without editing this file.
cd /d "%~dp0"

echo. >> logs\scraper.log
echo ======================================================= >> logs\scraper.log
echo [%DATE% %TIME%] Monthly refresh starting... >> logs\scraper.log

call venv\Scripts\activate

:: --- Taxonomies -------------------------------------------------------
:: Loaded first, because everything below classifies against them and the
:: scraper classifies each advert as it saves it. Both commands are
:: idempotent and read source-controlled CSVs, so running them every month
:: costs nothing and means a change to either file takes effect on the next
:: refresh without a manual step.
::
:: import_skills loads cs_skills.csv and then skill_aliases.csv, in that
:: order -- an alias cannot point at a skill that does not exist yet.
echo [%DATE% %TIME%] Loading skill and Market Role taxonomies... >> logs\scraper.log
python manage.py import_skills >> logs\scraper.log 2>&1
python manage.py load_market_roles >> logs\scraper.log 2>&1

:: --- Jobs -------------------------------------------------------------
:: The scraper stops on its own when a page returns no job cards, so a high
:: --max-pages is a ceiling rather than a promise of that many requests.
:: It also expires lapsed listings and records every student's skill gaps at
:: the end of a run; the gap refresh is deferred to the end of this script so
:: it reads settled data, hence --skip-skill-gap-refresh here.
echo [%DATE% %TIME%] Scraping jobs... >> logs\scraper.log
python manage.py scrape_jobs --max-pages 40 --max-jobs 32 --skip-skill-gap-refresh >> logs\scraper.log 2>&1

:: Collapse any advert stored twice before anything reads counts from the
:: table. Safe to re-run and cheap compared with the crawl itself.
echo [%DATE% %TIME%] Deduplicating... >> logs\scraper.log
python manage.py dedupe_scraped_listings >> logs\scraper.log 2>&1

:: Re-classify categories. save_scraped_job already categorises each listing
:: as it is saved, so this only catches rows whose title changed and company
:: listings, which the scraper never touches.
python manage.py recategorize_job_listings >> logs\scraper.log 2>&1

:: Re-extract skills across every stored advert.
::
:: JobSkill rows are the cached result of running the extractor once, at
:: scrape time. A new skill in cs_skills.csv, a new alias, or a correction to
:: the extractor's rules therefore leaves every existing advert holding the
:: old answer -- and the skill gap, the match score and the demand
:: percentages are all computed from those rows.
echo [%DATE% %TIME%] Re-extracting skills... >> logs\scraper.log
python manage.py reextract_job_skills >> logs\scraper.log 2>&1

:: Re-classify adverts into Market Roles for the same reason: each advert is
:: classified as it is saved, so a new reviewed alias in market_roles.csv or a
:: change to the classifier does not reach the adverts already stored.
:: Ambiguous and unclassified remain valid outcomes; nothing is guessed.
echo [%DATE% %TIME%] Classifying Market Roles... >> logs\scraper.log
python manage.py classify_market_roles >> logs\scraper.log 2>&1

:: What the market data can and cannot support, written to the log so a
:: coverage collapse is visible without opening the app.
python manage.py scrape_status >> logs\scraper.log 2>&1

:: --- Learning resources ----------------------------------------------
:: Has its own 30-day guard (DAYS_THRESHOLD in the command), so running it
:: monthly is exactly what it was written for. Resources back the skill-gap
:: recommendations, so letting them go stale degrades that page directly.
echo [%DATE% %TIME%] Scraping learning resources... >> logs\scraper.log
python manage.py scrape_resources >> logs\scraper.log 2>&1

:: --- Retention --------------------------------------------------------
:: Files whose database row is gone. The privacy notice promises a document
:: is removed when its record is, and the post_delete receivers keep that
:: promise for ordinary deletes; this catches anything a crash left behind.
echo [%DATE% %TIME%] Purging orphaned documents... >> logs\scraper.log
python manage.py purge_orphaned_documents >> logs\scraper.log 2>&1

:: --- Skill gaps -------------------------------------------------------
:: Run once, last, now that the market data, the skills extracted from it,
:: the Market Role classifications and the resources behind the
:: recommendations have all settled.
echo [%DATE% %TIME%] Recording skill gaps... >> logs\scraper.log
python manage.py refresh_skill_gaps >> logs\scraper.log 2>&1

echo [%DATE% %TIME%] Monthly refresh finished. >> logs\scraper.log
