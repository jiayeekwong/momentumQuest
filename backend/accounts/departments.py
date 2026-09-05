"""The faculty's departments, defined once.

These lists previously existed only in the frontend -- hardcoded separately in
the sign-up form and in the admin course form, which had already drifted apart
(one had "Compulsory", the other did not) while the backend accepted any string
at all. Three copies and no enforcement.

They live here now, are served by ``GET /api/auth/departments/`` so no page has
to carry its own copy, and are enforced by the serializers that write them.
"""

# What a student can belong to.
DEPARTMENTS = [
    "Artificial Intelligence",
    "Software Engineering",
    "Information Systems",
    "Computer System & Networking",
    "Multimedia",
]

# What a course can be filed under. A course may also be compulsory across
# every department, which is not something a student can *be*, so this is a
# superset rather than the same list.
COURSE_ONLY_DEPARTMENTS = [
    "Compulsory",
]

COURSE_DEPARTMENTS = DEPARTMENTS + COURSE_ONLY_DEPARTMENTS


def validate_department(value, allowed=None, field_name="department"):
    """Raise DRF ValidationError unless ``value`` is a known department.

    Blank is always allowed: department is optional on a student profile, and
    existing rows predate this list.
    """
    from rest_framework import serializers

    if not value:
        return ""

    choices = allowed if allowed is not None else DEPARTMENTS
    if value not in choices:
        raise serializers.ValidationError({
            field_name: [f"'{value}' is not a recognised department."]
        })
    return value
