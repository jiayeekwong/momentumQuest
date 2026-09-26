"""Database connection handling for work that runs far longer than a request.

Django is built around the request: a connection is opened, used within
milliseconds, and closed or health-checked at the next request boundary.
``CONN_MAX_AGE`` and ``CONN_HEALTH_CHECKS`` are both applied by the
``close_old_connections`` signal, which fires on request start and finish. A
management command never fires it, so a command holds one connection for its
whole life and nothing ever checks whether that connection is still alive.

That is fine for a command that runs for seconds against a local socket. It is
not fine for the market refresh, which crawls for tens of minutes -- hours at
full width -- making no query at all while it does, against a hosted Postgres
reached over the public internet. Nothing keeps an idle connection alive across
that: a serverless database suspends an idle compute, and an idle TCP flow is
the first thing a NAT or firewall forgets. The connection is gone long before
the crawl ends.

What that looked like was the first write after a crawl failing with

    server closed the connection unexpectedly

and then every later statement -- including the one meant to record the failure
-- failing with ``InterfaceError: connection already closed``, because psycopg2
marks the connection dead and Django keeps handing out the same object.

So this module offers the two operations that make long work survivable: let go
of a connection before a long stretch of not using one, and take a demonstrably
new one afterwards.
"""

import logging
import time

from django.db import connection

logger = logging.getLogger(__name__)

#: How hard to try before giving up on a connection. Name resolution and TLS to
#: a hosted database fail in bursts on some networks -- seconds to a couple of
#: minutes, then perfectly fine again. Measured on the network this runs from:
#: repeated lookups either all succeed or all fail, with nothing in between.
#:
#: A crawl that gives up on the first failed lookup turns one of those blips
#: into the end of a four-hour run, and it does it at the worst moment -- just
#: after a page was read, with the adverts still in hand. Waiting roughly a
#: minute and a half costs a pause; not waiting costs the run.
CONNECT_ATTEMPTS = 5
CONNECT_BACKOFF = 6


def release():
    """Close the connection before a long stretch with no database work.

    A connection that is not held cannot be dropped, which is the whole trick.
    Anything already written has been committed -- Django runs in autocommit --
    and the next query opens a new connection by itself.
    """
    _close_quietly()


def ensure(attempts=CONNECT_ATTEMPTS, backoff=CONNECT_BACKOFF):
    """Wait until the database is reachable, keeping any healthy connection.

    For the first query of a long job. Two resumed runs died there -- nothing
    crawled, nothing wrong, the run simply asked during one of the bursts and
    gave up.

    Unlike reconnect() this never discards a working connection, so it is safe
    to call from code that may already be inside a transaction. Replacing a
    connection mid-transaction is not a thing a caller can survive, and a
    startup check has no reason to.
    """
    for attempt in range(1, attempts + 1):
        try:
            connection.ensure_connection()
            if attempt > 1:
                logger.info("Database reachable on attempt %d.", attempt)
            return
        except Exception as exc:
            if attempt == attempts:
                raise
            wait = backoff * attempt
            logger.warning(
                "Could not reach the database (attempt %d of %d): %s. "
                "Retrying in %ds.", attempt, attempts, exc, wait)
            time.sleep(wait)


def reconnect(attempts=CONNECT_ATTEMPTS, backoff=CONNECT_BACKOFF):
    """Open a new connection, whatever state the old one was left in.

    ``close()`` alone is not enough after a failure. When a connection breaks
    inside an atomic block Django sets ``closed_in_transaction`` and leaves the
    dead object in place; ``ensure_connection`` then sees a connection that is
    not ``None`` and declines to reopen, so every later query fails the same
    way. ``connect()`` resets that state and establishes a new connection
    unconditionally, which is why this does not rely on a lazy reopen.

    Retries, because the failure this exists to survive is transient by nature.
    Each attempt waits longer than the last, and the last failure is raised
    rather than swallowed: a caller that genuinely cannot reach the database has
    nothing to fall back on, and saying so beats continuing quietly.
    """
    for attempt in range(1, attempts + 1):
        _close_quietly()
        try:
            connection.connect()
            if attempt > 1:
                logger.info("Database reachable again on attempt %d.", attempt)
            return
        except Exception as exc:
            if attempt == attempts:
                raise
            wait = backoff * attempt
            logger.warning(
                "Could not reach the database (attempt %d of %d): %s. "
                "Retrying in %ds.", attempt, attempts, exc, wait)
            time.sleep(wait)


def _close_quietly():
    """Discard the current connection; never raise.

    Closing a connection the server has already dropped can itself fail, and at
    this point the object is being thrown away either way.
    """
    try:
        connection.close()
    except Exception:
        connection.connection = None
