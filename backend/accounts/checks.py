"""Checks for accounts that exist but were never finished.

A user row carries the login and the role. Everything the application reads
about the person -- a student's name and department, a company's details, the
administrator a record is attributed to -- lives in a separate table joined
one-to-one, and only two code paths ever create those: the registration
serializer for students and companies, and `manage.py create_admin` for
administrators.

`createsuperuser` creates neither, and until the profile inlines were added
neither did the Django admin. So an account could hold every administrator
power, pass every permission check, and have nothing to attribute its work to.
The first anyone knew of it was a 500 on publishing an announcement, weeks
after the account was made.

That failure is now a clear 409 rather than a server error, but the account is
still broken and still needs a person to fix it. This says so at the point
where somebody can act -- `manage.py check`, and every management command that
runs the checks first -- instead of waiting for the administrator to try to do
something.

Warnings rather than errors: a half-built account is a thing to repair, not a
reason to refuse to start. A deployment with one is still a working deployment
for everybody else.
"""

from django.core.checks import Warning, register


def _unprofiled(model, role, related):
    """Users of `role` with no row in the profile table, newest first.

    Returns an empty list if the tables are not there yet. Checks run before
    `migrate` on a fresh database, and a check that explodes at that moment
    stops the deployment it was meant to help.
    """
    from django.db import DatabaseError

    try:
        return list(model.objects
                    .filter(role=role, **{f"{related}__isnull": True})
                    .values_list("email", flat=True)[:10])
    except DatabaseError:
        return []


@register()
def accounts_have_their_profiles(app_configs, **kwargs):
    from .models import User

    checks = (
        (User.Role.ADMIN, "admin_profile", "AdminProfile",
         'manage.py create_admin --email {email} --name "<display name>" '
         '--promote'),
        (User.Role.STUDENT, "student_profile", "Student",
         "add the Student profile on the user's page in the Django admin"),
        (User.Role.COMPANY, "company_profile", "Company",
         "add the Company profile on the user's page in the Django admin"),
    )

    messages = []
    for role, related, profile_model, remedy in checks:
        emails = _unprofiled(User, role, related)
        if not emails:
            continue
        listed = ", ".join(emails)
        messages.append(Warning(
            f"{len(emails)} {role} account(s) have no {profile_model}: {listed}",
            hint=("Such an account passes every permission check and then "
                  "fails the moment something needs the profile. Fix it with: "
                  + remedy.format(email=emails[0])),
            id=f"accounts.W{100 + len(messages) + 1}",
        ))
    return messages
