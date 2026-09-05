"""Create a MomentumQuest administrator.

The only supported way to make one. Public registration accepts students and
companies only -- it used to accept ADMIN, which meant anyone could POST
role="ADMIN", verify their own email address, and gain certificate review and
access to every student's identity documents.

Both facts an administrator needs are set here together: ``role="ADMIN"``,
which the application reads, and ``is_staff``, which is only ever granted from
a shell with database access. IsAdminUserRole requires both, so neither alone
is enough.

    python manage.py create_admin --email you@uni.edu --name "Your Name"

The password is read from ADMIN_PASSWORD in the environment, from the terminal
with --prompt-password, or generated and printed once. It is never taken from
the command line, where it would land in shell history and the process table.
"""

import getpass
import os
import secrets

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import AdminProfile, User


class Command(BaseCommand):
    help = "Create an administrator account (role=ADMIN and is_staff)"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument(
            "--superuser", action="store_true",
            help="Also grant is_superuser, for Django admin access.")
        parser.add_argument(
            "--promote", action="store_true",
            help="Promote an existing account instead of refusing.")
        parser.add_argument(
            "--prompt-password", action="store_true",
            help="Read the password from the terminal instead of "
                 "ADMIN_PASSWORD or a generated one.")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        name = options["name"].strip()
        if not email or not name:
            raise CommandError("--email and --name are both required.")

        existing = User.objects.filter(email=email).first()
        if existing and not options["promote"]:
            raise CommandError(
                f"{email} already exists (role={existing.role}, "
                f"is_staff={existing.is_staff}). Pass --promote to grant "
                f"administrator rights to this account."
            )

        password = os.environ.get("ADMIN_PASSWORD") or ""
        generated = False
        if not password and options["prompt_password"]:
            # Only on an explicit flag. Reading stdin unprompted makes the
            # command unusable from a script and hangs a test runner, which is
            # exactly what a bootstrap command must not do.
            password = getpass.getpass("Password for the new admin: ")
        if not password and not existing:
            password = secrets.token_urlsafe(16)
            generated = True

        if existing:
            user = existing
            user.role = User.Role.ADMIN
            user.is_staff = True
            user.is_active = True
            user.email_verified = True
            if options["superuser"]:
                user.is_superuser = True
            if password:
                user.set_password(password)
            user.save()
        else:
            user = User.objects.create_user(
                email=email,
                password=password,
                role=User.Role.ADMIN,
                is_staff=True,
                is_active=True,
                email_verified=True,
                is_superuser=bool(options["superuser"]),
            )

        AdminProfile.objects.update_or_create(
            user=user, defaults={"admin_name": name})

        self.stdout.write(self.style.SUCCESS(
            f"{'Promoted' if existing else 'Created'} administrator {email} "
            f"(is_staff=True, is_superuser={user.is_superuser})."))
        if generated:
            self.stdout.write(self.style.WARNING(
                f"Generated password (shown once): {password}"))
