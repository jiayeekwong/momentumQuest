from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group

from .forms import UserChangeForm, UserCreationForm
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

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """The user admin, with Django's password handling rather than a text box.

    Registered with `admin.site.register(User)` before this, which gave it the
    default ModelAdmin: a plain ModelForm over every editable field, including
    `password`. AbstractBaseUser declares that as an ordinary CharField, so the
    Add User page showed one visible password box and stored whatever was typed,
    unhashed. Those accounts could not log in, and their passwords sat in the
    database in clear text.

    Django's UserAdmin is the fix, but not unmodified: its add_fieldsets name a
    `username` field this model does not have, so both fieldsets are declared
    here against `email`.

    `groups` and `user_permissions` are deliberately absent. This project
    authorises on the custom `role` field -- which is why Group is unregistered
    at the bottom of this module -- and offering permission widgets that nothing
    reads would invite an administrator to grant access that has no effect.
    """

    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    ordering = ("email",)
    list_display = ("email", "role", "is_active", "email_verified", "is_staff",
                    "created_time")
    list_filter = ("role", "is_active", "is_staff", "is_superuser",
                   "email_verified")
    search_fields = ("email",)
    readonly_fields = ("last_login",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Role and access", {
            "fields": ("role", "email_verified", "is_active", "is_staff",
                       "is_superuser"),
        }),
        ("Dates", {"fields": ("last_login", "created_time")}),
    )

    # usable_password is Django's own control for creating an account that
    # cannot be signed into with a password; it comes from AdminUserCreationForm
    # and has to be listed or the admin will not render it.
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "role", "usable_password", "password1",
                       "password2"),
        }),
    )
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
