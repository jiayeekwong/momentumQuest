# MomentumQuest backend, as Render runs it.
#
# Two things make this image different from a plain Django image.
#
# It carries a browser. The market scraper drives Chromium through Selenium, so
# Chromium and its driver are installed here, from the same Debian snapshot, and
# their paths are exported. That is what lets CHROMEDRIVER_PATH be set, which
# takes ChromeDriverManager out of the runtime path entirely -- it fetches a
# version manifest over the network on every call and raises when it cannot, so
# leaving it in means a network blip fails a scrape that never reached the job
# board. That exact failure was observed during release validation.
#
# And it does not bootstrap itself. No migrate, no import_skills, no
# import_resources at startup. Those are release operations run once against a
# new database; a web process that ran them would re-run them on every restart,
# on every scaled-up instance, and concurrently during a rolling deploy. See
# docs/deployment-runbook.md for the sequence and when each part applies.

# Pinned to the Debian release, not the floating slim tag. The apt packages
# below are Debian's, so a base that silently moves to the next Debian would
# change chromium's version and packaging under a build that looks unchanged.
FROM python:3.14-slim-trixie

# Chromium and chromium-driver come from the same apt snapshot, so the driver
# matches the browser without a version lookup. libnss3 and the font package
# are not optional: headless Chromium exits immediately without them, and
# without fonts it renders blank pages that read as an empty job board rather
# than as a missing dependency.
RUN apt-get update && apt-get install --no-install-recommends -y \
        chromium \
        chromium-driver \
        libnss3 \
        libxss1 \
        fonts-liberation \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Read by scrape_jobs.scraper.create_driver. Set here rather than in render.yaml
# so the image is self-describing: whatever runs it gets a working browser
# without having to know these paths.
ENV CHROME_BINARY=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver

# PYTHONUNBUFFERED so Render's log stream shows output as it happens rather
# than when a buffer fills -- which matters most for the long scraper run.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements first, so a code change does not reinstall the dependency tree.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Baked into the image so a restart does not depend on the build step having
# run, and so WhiteNoise has the admin's CSS to serve when DEBUG is false.
# DJANGO_SECRET_KEY is a build-time placeholder: settings.py refuses to start on
# the development key when DEBUG is false, and collectstatic needs the settings
# to import. The real key comes from the environment at run time.
RUN DJANGO_DEBUG=false \
    DJANGO_SECRET_KEY=build-time-placeholder-not-used-at-runtime \
    python manage.py collectstatic --noinput

# Certificates carry a student's full name and identification number, so they
# are written outside MEDIA_ROOT and served only through an ownership-checked
# view. In production this is a mounted Render disk; the directory is created
# here so the image also runs without one, in which case the contents are
# ephemeral and that is a deployment error rather than a silent data loss.
RUN mkdir -p /var/data/private_media

# Non-root, and it must own the media path or uploads fail at write time rather
# than at deploy time.
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app /var/data
USER app

EXPOSE 8000

# Render supplies $PORT; the default keeps `docker run` usable without it.
# Shell form on purpose, so $PORT is expanded.
CMD gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-2} \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
