"""Bootstrap a fresh database, having first said out loud which one it is.

    python manage.py bootstrap_database --confirm-host neon.tech
    python manage.py bootstrap_database --confirm-host localhost --dry-run

Two mistakes this exists to make difficult.

**Bootstrapping the wrong database.** The production bootstrap is run from a
workstation with its environment pointed at the hosted database, which means a
forgotten environment variable runs it against the developer's own database
instead -- or, worse, a stale shell runs a later command against production
believing it is local. ``--confirm-host`` makes the operator state where they
think they are pointed and refuses when that disagrees with reality. It is
required precisely because a flag that can be omitted is a flag that gets
omitted.

**Missing a step.** ``migrate``, ``import_skills`` and ``import_resources`` all
succeed without ``load_market_roles`` and leave MarketRole at 0, which silently
empties career-area scoping on the skill-gap page. No error, just a page that
looks thin. Encoding the sequence here means the easy-to-forget step cannot be
forgotten, and the reference counts are verified rather than eyeballed.

Nothing here is destructive: every command it runs is idempotent, and it writes
no user data. It refuses a non-empty database anyway, because a bootstrap aimed
at a populated database is a sign the operator believes something untrue about
where they are.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

#: The reference data a bootstrapped database must contain, from the committed
#: seeds. Verified rather than reported: a count that silently drifts is how a
#: deployment ends up subtly different from every other one.
EXPECTED = (
    ("scrape_jobs", "MarketRole", 32),
    ("scrape_jobs", "MarketRoleAlias", 235),
    ("resources", "CourseCatalogue", 5794),
    ("resources", "LearningResource", 20434),
    ("resources", "RejectedResourceMapping", 11),
)

#: In order. load_market_roles is third rather than last because the aliases it
#: loads are what later classification reads.
SEQUENCE = (
    ("migrate", {"interactive": False}),
    ("createcachetable", {}),
    ("import_skills", {}),
    ("load_market_roles", {}),
    ("import_resources", {}),
)


class Command(BaseCommand):
    help = ("Run the first-deployment database bootstrap, after confirming "
            "which database is connected.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm-host", required=True, metavar="SUBSTRING",
            help=("A substring of the host you believe you are connected to, "
                  "e.g. 'neon.tech' or 'localhost'. Refuses if it does not "
                  "match the live connection."))
        parser.add_argument(
            "--dry-run", action="store_true", default=False,
            help="Show the target and the plan, then stop.")
        parser.add_argument(
            "--allow-populated", action="store_true", default=False,
            help=("Proceed even though reference data is already present. "
                  "Every step is idempotent; the refusal exists because a "
                  "bootstrap aimed at a populated database usually means the "
                  "operator is not where they think they are."))

    # ---------------------------------------------------------------- target

    def _target(self):
        settings_dict = connection.settings_dict
        return {
            "host": settings_dict.get("HOST") or "(local socket)",
            "name": settings_dict.get("NAME"),
            "user": settings_dict.get("USER"),
            "port": settings_dict.get("PORT") or "(default)",
            "sslmode": (settings_dict.get("OPTIONS") or {}).get(
                "sslmode", "(unset)"),
        }

    def _announce(self, target):
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            "  About to bootstrap this database:"))
        self.stdout.write("")
        for label in ("host", "name", "user", "port", "sslmode"):
            self.stdout.write(f"      {label:9} {target[label]}")

        # Read from the server, not from settings: this is the one line that
        # cannot be wrong about which database is actually connected.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), current_user, "
                "inet_server_addr()::text, version()")
            database, user, address, version = cursor.fetchone()
        self.stdout.write("")
        self.stdout.write("  The server itself reports:")
        self.stdout.write(f"      database  {database}")
        self.stdout.write(f"      user      {user}")
        self.stdout.write(f"      address   {address or '(local socket)'}")
        self.stdout.write(f"      version   {version.split(',')[0]}")
        self.stdout.write("")

    def _populated(self):
        """Reference rows already present, by name, without importing models."""
        from django.apps import apps

        found = {}
        for app_label, model_name, _expected in EXPECTED:
            model = apps.get_model(app_label, model_name)
            count = model.objects.count()
            if count:
                found[model_name] = count
        return found

    # ------------------------------------------------------------------ main

    def handle(self, *args, **options):
        target = self._target()
        self._announce(target)

        claimed = options["confirm_host"].strip().lower()
        actual = str(target["host"]).lower()
        if claimed not in actual:
            raise CommandError(
                f"--confirm-host {claimed!r} does not appear in the connected "
                f"host {target['host']!r}. Nothing was changed.\n\n"
                f"        You are not connected to the database you think you "
                f"are. Check the environment before re-running.")

        self.stdout.write(self.style.SUCCESS(
            f"  Confirmed: {claimed!r} matches the connected host."))

        if options["dry_run"]:
            self.stdout.write("")
            self.stdout.write("  Would run, in order:")
            for name, _kwargs in SEQUENCE:
                self.stdout.write(f"      manage.py {name}")
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "  Dry run. Nothing was changed."))
            return

        try:
            existing = self._populated()
        except Exception:
            # Tables do not exist yet, which is the normal case here.
            existing = {}

        if existing and not options["allow_populated"]:
            summary = ", ".join(f"{k}={v}" for k, v in sorted(existing.items()))
            raise CommandError(
                f"This database already holds reference data ({summary}). "
                f"Nothing was changed.\n\n"
                f"        Every bootstrap step is idempotent, so this refusal "
                f"is about intent rather than safety: a bootstrap aimed at a "
                f"populated database usually means the environment is pointing "
                f"somewhere unexpected. Pass --allow-populated to proceed.")

        for name, kwargs in SEQUENCE:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(f"  manage.py {name}"))
            call_command(name, **kwargs)

        self._verify()

    def _check_domain_invariants(self):
        """Rules the reference data must satisfy, beyond matching the seed.

        Deliberately separate from the seed digests. A digest proves the
        database equals the file; it says nothing about whether the file is
        itself coherent. Both were needed here: a role reached the seed with no
        broad_area, and the digest was perfectly happy because the database
        agreed with it.

        broad_area drives career-area scoping, so a role without one cannot be
        browsed under any area -- it is present, counted, and unreachable.

        Empty, NULL and whitespace-only are treated alike. The field is
        blank=True and not null=True, so NULL should not occur, but a value of
        " " would pass a bare exclude(broad_area="") while being just as
        unbrowsable.
        """
        from django.apps import apps

        MarketRole = apps.get_model("scrape_jobs", "MarketRole")
        offenders = sorted(
            name for name, area in MarketRole.objects.values_list(
                "name", "broad_area")
            if not (area or "").strip()
        )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("  Domain invariants"))
        self.stdout.write(
            f"      {'roles with no broad_area':26} {len(offenders):>7}")

        if offenders:
            raise CommandError(
                "Every Market Role must belong to exactly one non-empty broad "
                "area, and these do not:"
                + "\n    " + ("\n    ").join(offenders)
                + "\n\n        A role with no broad area is counted but "
                  "unreachable: career-area scoping has nowhere to show it. "
                  "Give each one an existing area in data/market_roles.csv and "
                  "re-run load_market_roles.")

    def _verify(self):
        from django.apps import apps

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("  Reference data"))

        wrong = []
        for app_label, model_name, expected in EXPECTED:
            actual = apps.get_model(app_label, model_name).objects.count()
            ok = actual == expected
            if not ok:
                wrong.append((model_name, actual, expected))
            mark = "" if ok else "   <-- expected %d" % expected
            self.stdout.write(f"      {model_name:26} {actual:>7}{mark}")

        if wrong:
            raise CommandError(
                "The bootstrapped database does not match the committed seeds: "
                + "; ".join(f"{n} is {a}, expected {e}" for n, a, e in wrong)
                + ".\n\n        A database that cannot reproduce its own seeds "
                  "is not reproducible anywhere else either. Do not deploy "
                  "against it.")

        # The counts agreeing is necessary and not sufficient -- these compare a
        # deterministic sorted digest of every field, which is what catches a
        # row that is present but wrong.
        self._check_domain_invariants()

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("  Seed digests"))
        call_command("export_skills", check=True)
        # Market roles went without a check for a while and drifted -- three
        # reviewed aliases and one role were approved into a database and never
        # written back. Included here so a bootstrap cannot pass while the
        # taxonomy silently differs from the file.
        call_command("load_market_roles", check=True)
        call_command("export_resources", check=True)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            "  Bootstrap complete and verified against the committed seeds."))
        self.stdout.write(
            "  Production has no adverts yet: run refresh_market_data next.")
