"""One server-side definition of who can see an announcement."""

from django.db.models import Q

from accounts.models import User

from .models import Announcement


def published_announcements():
    return Announcement.objects.filter(
        approval_status=Announcement.ApprovalStatus.APPROVED,
        publish_time__isnull=False,
    )


def visible_announcements_for(user, queryset=None):
    """Scope announcements for a user, including department membership."""
    rows = queryset if queryset is not None else published_announcements()
    if user.role == User.Role.STUDENT:
        department_id = getattr(
            getattr(user, "student_profile", None), "department_id", None)
        student_filter = (
            Q(audience=Announcement.AudienceChoice.EVERYONE)
            | Q(
                audience=Announcement.AudienceChoice.STUDENTS,
                target_departments__isnull=True,
            )
        )
        if department_id:
            student_filter |= Q(
                audience=Announcement.AudienceChoice.STUDENTS,
                target_departments=department_id,
            )
        return rows.filter(student_filter).distinct()
    if user.role == User.Role.COMPANY:
        return rows.filter(audience__in=[
            Announcement.AudienceChoice.EVERYONE,
            Announcement.AudienceChoice.COMPANIES,
        ])
    return rows

