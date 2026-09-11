# MomentumQuest backend, as Render Free runs it: the Django API and nothing else.
#
# No browser. An earlier version of this image installed Chromium so the market
# scraper could run here, and that does not fit the deployment: headless
# Chromium wants 400-500MB of its own on top of Django, which exceeds a free
# instance, and the image was an order of magnitude larger for a job that runs
# once a month. Scraping moved to GitHub Actions, with a developer workstation
# as the fallback, and both talk to the same hosted PostgreSQL. The scraper code
# stays in the repository and is unchanged -- see docs/deployment-runbook.md.
#
# No persistent disk either. Free instance storage is ephemeral, so private
# documents live in object storage; see resources/private_storage.py.
#
# And it does not bootstrap itself. No migrate, no import_skills, no
# import_resources at startup. Those are release operations run once against a
# new database; a web process that ran them would repeat them on every restart
# and concurrently during a rolling deploy.

# Pinned to the Debian release rather than the floating slim tag, so the apt
# packages below cannot change underneath a build that looks unchanged.
FROM python:3.14-slim-trixie

# libpq5 for psycopg. curl earns its place as the only way to diagnose outbound
# connectivity from inside a container with no shell access on the free plan.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# PYTHONUNBUFFERED so the platform's log stream shows output as it happens
# rather than when a buffer fills.
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

# Non-root.
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# $PORT is supplied by the platform; the default keeps `docker run` usable
# without it. Shell form on purpose, so $PORT is expanded.
#
# Two workers, which is why the cache must be shared rather than per-process --
# throttle history lives there, and a per-process cache would make the real
# login rate limit the configured rate times the worker count.
CMD gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-2} \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
