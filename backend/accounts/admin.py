from django.contrib import admin
from django.contrib.auth.models import Group
from .models import (
    AdminProfile,
    Company,
    PrivacyAuditLog,
    SkillGap,
    Student,
    RoleTerminologyFeedback,
    StudentTargetRole,
    User,
    UserConsent,
)

admin.site.register(User)
admin.site.register(Student)
admin.site.register(Company)
admin.site.register(AdminProfile)
admin.site.register(StudentTargetRole)
admin.site.register(RoleTerminologyFeedback)
admin.site.register(SkillGap)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Browsable but immutable.

    Consent records and audit entries are evidence. If they can be edited from
    the admin site they prove nothing, so the only supported operation is
    reading them.
    """

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserConsent)
class UserConsentAdmin(ReadOnlyAdmin):
    list_display  = ("user", "consent_type", "notice_version", "accepted",
                     "accepted_at", "source")
    list_filter   = ("consent_type", "accepted", "notice_version", "source")
    search_fields = ("user__email",)
    date_hierarchy = "created_at"


@admin.register(PrivacyAuditLog)
class PrivacyAuditLogAdmin(ReadOnlyAdmin):
    list_display  = ("timestamp", "actor_user", "action", "target_user",
                     "resource_type", "resource_id")
    list_filter   = ("action", "resource_type")
    search_fields = ("actor_user__email", "target_user__email")
    date_hierarchy = "timestamp"

# Hide Django's built-in Groups from the admin — this project uses the custom
# `role` field for authorization, not Django Groups.
admin.site.unregister(Group)
